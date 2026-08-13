from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import threading
from urllib.request import urlopen
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = TOOLS_ROOT / "session_monitor.py"


def load_module():
    spec = importlib.util.spec_from_file_location("session_monitor", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = load_module()


class SessionMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="session-monitor-"))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.rollout = self.root / "rollout-primary.jsonl"
        self.write_event({
            "type": "session_meta",
            "payload": {
                "id": "primary",
                "timestamp": "2026-07-24T12:00:00Z",
                "source": "cli",
            },
        })

    def write_event(self, event: dict, newline: bool = True) -> None:
        with self.rollout.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event))
            if newline:
                handle.write("\n")

    def append_turn(self, user: str, assistant: str = "", commands: list[str] | None = None) -> None:
        self.write_event({"type": "event_msg", "payload": {"type": "task_started"}})
        self.write_event({
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user}],
            },
        })
        for command in commands or []:
            self.write_event({
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "arguments": json.dumps({"cmd": command}),
                },
            })
        self.write_event({
            "type": "event_msg",
            "payload": {"type": "task_complete", "last_agent_message": assistant},
        })

    def append_token_count(self, total: int, *, cached: int = 0, output: int = 10) -> None:
        self.write_event({
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": total - output,
                        "cached_input_tokens": cached,
                        "output_tokens": output,
                        "reasoning_output_tokens": 2,
                        "total_tokens": total,
                    },
                    "last_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 80,
                        "output_tokens": 10,
                        "reasoning_output_tokens": 2,
                        "total_tokens": 110,
                    },
                    "model_context_window": 1000,
                },
            },
        })

    def parser(self, state=None):
        return mod.IncrementalRolloutParser(
            self.rollout,
            mod.load_category_config(mod.DEFAULT_CATEGORY_CONFIG),
            state,
        )

    def monitor(self):
        original_state_root = mod.STATE_ROOT
        mod.STATE_ROOT = self.root / "state"
        self.addCleanup(lambda: setattr(mod, "STATE_ROOT", original_state_root))
        return mod.SessionMonitor(self.root, rollout=self.rollout)

    def test_incremental_append_does_not_duplicate_completed_turns(self) -> None:
        self.append_turn("Plan the implementation.")
        state = self.parser().update()
        self.assertEqual(len(state.turns), 1)
        first_offset = state.offset

        self.append_turn(
            "Build the dashboard.",
            commands=["bash tools/helpers/rule_discovery.sh monitor"],
        )
        state = self.parser(state).update()

        self.assertGreater(state.offset, first_offset)
        self.assertEqual(len(state.turns), 2)
        self.assertEqual(state.turns[1]["helper_invocations"], ["rule_discovery.sh"])

    def test_helper_detection_is_case_insensitive_for_repository_paths(self) -> None:
        detect = mod.helper_detector(["tools/", "scripts/"])
        self.assertEqual(
            detect("python3 Assets/JF/Tools/ai/work_plan.py status"),
            ["work_plan.py"],
        )

    def test_exec_tool_name_and_embedded_commands_are_descriptive(self) -> None:
        raw = 'const rs=await Promise.all(cmds.map(c=>tools.exec_command(c))); text(await tools.apply_patch(patch)); const x={cmd:"python3 Assets/JF/Tools/ai/work_plan.py status"};'
        self.assertEqual(
            mod.descriptive_tool_name("exec", raw),
            "exec → exec_command, apply_patch",
        )
        self.assertEqual(
            mod.extract_tool_commands(raw),
            ["python3 Assets/JF/Tools/ai/work_plan.py status"],
        )

    def test_partial_json_line_is_deferred_until_completed(self) -> None:
        event = {"type": "event_msg", "payload": {"type": "task_started"}}
        encoded = json.dumps(event)
        with self.rollout.open("a", encoding="utf-8") as handle:
            handle.write(encoded[:15])
        state = self.parser().update()
        self.assertFalse(state.turn_in_progress)
        self.assertTrue(state.partial_line)

        with self.rollout.open("a", encoding="utf-8") as handle:
            handle.write(encoded[15:] + "\n")
        state = self.parser(state).update()
        self.assertTrue(state.turn_in_progress)
        self.assertEqual(state.partial_line, "")

    def test_truncation_rebuilds_from_rollout_source(self) -> None:
        self.append_turn("Plan the implementation.")
        state = self.parser().update()
        self.assertEqual(len(state.turns), 1)

        self.rollout.write_text(
            json.dumps({
                "type": "session_meta",
                "payload": {"id": "replacement", "timestamp": "2026-07-24T13:00:00Z", "source": "cli"},
            }) + "\n",
            encoding="utf-8",
        )
        state = self.parser(state).update()

        self.assertEqual(state.session_id, "replacement")
        self.assertEqual(state.turns, [])

    def test_incidental_documentation_turn_does_not_create_phase(self) -> None:
        turns = [
            {"category": "implementation"},
            {"category": "doc-maintenance"},
            {"category": "implementation"},
        ]

        phases = mod.infer_phase_history(turns)

        self.assertEqual([phase["name"] for phase in phases], ["Implementation"])
        self.assertEqual(phases[0]["end_turn"], 3)

    def test_phase_transition_and_split_warning_are_actionable(self) -> None:
        turns = []
        turns.extend({"category": "review", "helper_invocations": []} for _ in range(7))
        turns.extend({"category": "implementation", "helper_invocations": []} for _ in range(7))
        turns.extend({"category": "debugging", "helper_invocations": []} for _ in range(7))
        phases = mod.infer_phase_history(turns)

        warning = mod.warning_state(turns, phases, None)

        self.assertEqual(warning["severity"], "split")
        self.assertIn("review transitioned into implementation", warning["triggered_rules"])
        self.assertTrue(warning["recommended_action"])

    def test_child_rollouts_are_grouped_under_primary(self) -> None:
        child = self.root / "rollout-child.jsonl"
        events = [
            {
                "type": "session_meta",
                "payload": {
                    "id": "child",
                    "timestamp": "2026-07-24T12:01:00Z",
                    "source": {"subagent": {"thread_spawn": {
                        "parent_thread_id": "primary",
                        "agent_path": "/root/review",
                        "depth": 1,
                    }}},
                },
            },
            {"type": "event_msg", "payload": {"type": "task_started"}},
        ]
        child.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

        activity = mod.child_activity(self.root, "primary", None)

        self.assertEqual(activity["active"], 1)
        self.assertEqual(activity["completed"], 0)
        self.assertEqual(activity["items"][0]["path"], "/root/review")

    def test_json_contract_excludes_raw_prompt_and_rollout_path(self) -> None:
        self.append_turn("secret prompt: API_KEY=abc", "secret response")
        original_state_root = mod.STATE_ROOT
        mod.STATE_ROOT = self.root / "state"
        self.addCleanup(lambda: setattr(mod, "STATE_ROOT", original_state_root))

        snapshot = mod.SessionMonitor(self.root, rollout=self.rollout).snapshot()
        encoded = json.dumps(snapshot)

        self.assertEqual(snapshot["contract_version"], 4)
        self.assertNotIn("secret prompt", encoded)
        self.assertNotIn("secret response", encoded)
        self.assertNotIn(str(self.rollout), encoded)

    def test_explicit_phase_override_and_warning_acknowledgement_persist(self) -> None:
        self.append_turn("Plan the implementation.")
        original_state_root = mod.STATE_ROOT
        mod.STATE_ROOT = self.root / "state"
        self.addCleanup(lambda: setattr(mod, "STATE_ROOT", original_state_root))
        monitor = mod.SessionMonitor(self.root, rollout=self.rollout)

        monitor.set_phase("Validation")
        monitor.dismiss_warning()
        snapshot = monitor.snapshot()

        self.assertEqual(snapshot["phase"]["current"], "Validation")
        self.assertEqual(snapshot["phase"]["source"], "confirmed")
        self.assertTrue(snapshot["warning"]["acknowledged"])

    def test_phase_history_rename_merge_and_reset_persist(self) -> None:
        self.append_turn("Review the staged changes.")
        self.append_turn("Implement the requested fix.")
        monitor = self.monitor()

        monitor.edit_phase("rename", 1, "Validation")
        renamed = monitor.snapshot()
        monitor.edit_phase("merge", 1)
        merged = monitor.snapshot()
        monitor.edit_phase("reset", 0)
        reset = monitor.snapshot()

        self.assertEqual(renamed["phase"]["history"][1]["name"], "Validation")
        self.assertEqual(renamed["phase"]["history"][1]["confidence"], "confirmed")
        self.assertEqual(len(merged["phase"]["history"]), 1)
        self.assertEqual(merged["phase"]["history"][0]["confidence"], "confirmed")
        self.assertEqual(
            [phase["name"] for phase in reset["phase"]["history"]],
            ["Review", "Implementation"],
        )

    def test_warning_threshold_overrides_and_reset(self) -> None:
        self.append_turn("Implement the monitor.")
        self.append_token_count(500)
        monitor = self.monitor()

        monitor.set_thresholds({
            "turns": 1,
            "categories": 8,
            "phases": 8,
            "helper_coverage": 0.1,
            "helper_min_turns": 8,
            "context_ratio": 0.05,
        })
        overridden = monitor.snapshot()
        monitor.reset_thresholds()
        reset = monitor.snapshot()

        self.assertTrue(overridden["warning"]["thresholds_overridden"])
        self.assertEqual(overridden["warning"]["severity"], "advisory")
        self.assertIn("1+ completed turns", overridden["warning"]["triggered_rules"])
        self.assertFalse(reset["warning"]["thresholds_overridden"])
        self.assertEqual(reset["warning"]["thresholds"], mod.DEFAULT_THRESHOLDS)

    def test_continuation_prompt_is_user_authored_and_filters_absolute_paths(self) -> None:
        self.append_turn("secret source prompt", "secret response")
        monitor = self.monitor()

        result = monitor.continuation_prompt({
            "goal": "Finish session history.",
            "completed": "Built the API.",
            "remaining": "Wire the dashboard.",
            "constraints": "Keep data local.",
            "files": "tools/session/session_monitor.py\n/etc/passwd\n~/secret\n../../private",
        })

        self.assertIn("Goal: Finish session history.", result["prompt"])
        self.assertIn("- tools/session/session_monitor.py", result["prompt"])
        self.assertNotIn("/etc/passwd", result["prompt"])
        self.assertNotIn("~/secret", result["prompt"])
        self.assertNotIn("../../private", result["prompt"])
        self.assertNotIn("secret source prompt", result["prompt"])
        self.assertNotIn("secret response", result["prompt"])

    def test_recent_sessions_exclude_delegated_rollouts_and_can_be_selected(self) -> None:
        self.append_turn("Implement the first session.")
        second = self.root / "rollout-second.jsonl"
        second.write_text(
            json.dumps({
                "type": "session_meta",
                "payload": {
                    "id": "second",
                    "timestamp": "2026-07-24T13:00:00Z",
                    "source": "cli",
                },
            }) + "\n",
            encoding="utf-8",
        )
        child = self.root / "rollout-z-child.jsonl"
        child.write_text(json.dumps({
            "type": "session_meta",
            "payload": {
                "id": "child",
                "timestamp": "2026-07-24T13:01:00Z",
                "source": {"subagent": {"thread_spawn": {"parent_thread_id": "second"}}},
            },
        }) + "\n", encoding="utf-8")
        original_state_root = mod.STATE_ROOT
        mod.STATE_ROOT = self.root / "state"
        self.addCleanup(lambda: setattr(mod, "STATE_ROOT", original_state_root))
        monitor = mod.SessionMonitor(self.root)

        history = monitor.recent_sessions()
        monitor.select_session("primary")
        selected = monitor.snapshot()

        self.assertEqual({item["id"] for item in history["sessions"]}, {"primary", "second"})
        self.assertTrue(all(item["repository"] for item in history["sessions"]))
        self.assertEqual(selected["session"]["id"], "primary")
        self.assertFalse(selected["session"]["is_latest"])

    def test_sse_endpoint_emits_sanitized_state_event(self) -> None:
        self.append_turn("secret source prompt", "secret response")
        monitor = self.monitor()
        server = mod.create_server(monitor, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/events",
            timeout=5,
        ) as response:
            event_line = response.readline().decode()
            data_line = response.readline().decode()

        self.assertEqual(event_line, "event: state\n")
        self.assertTrue(data_line.startswith("data: "))
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertEqual(payload["contract_version"], 4)
        self.assertNotIn("secret source prompt", json.dumps(payload))

    def test_token_totals_context_and_per_turn_delta_are_incremental(self) -> None:
        self.write_event({"type": "event_msg", "payload": {"type": "task_started"}})
        self.append_token_count(500, cached=300, output=20)
        self.write_event({"type": "event_msg", "payload": {"type": "task_complete"}})
        state = self.parser().update()

        self.write_event({"type": "event_msg", "payload": {"type": "task_started"}})
        self.append_token_count(800, cached=500, output=35)
        self.write_event({"type": "event_msg", "payload": {"type": "task_complete"}})
        state = self.parser(state).update()
        tokens = mod.token_payload(state)

        self.assertEqual(state.turns[0]["token_usage"]["total_tokens"], 500)
        self.assertEqual(state.turns[1]["token_usage"]["total_tokens"], 300)
        self.assertEqual(tokens["session"]["total_tokens"], 800)
        self.assertEqual(tokens["session"]["uncached_input_tokens"], 265)
        self.assertEqual(tokens["latest_model_call"]["total_tokens"], 110)
        self.assertEqual(tokens["context"]["used_ratio"], 0.1)
        self.assertEqual(
            [point["total_tokens"] for point in tokens["trend"]],
            [500, 300],
        )
        self.assertEqual(tokens["trend"][1]["context_used_ratio"], 0.1)
        self.assertNotIn("user_message", tokens["trend"][0])
        self.assertNotIn("last_agent_message", tokens["trend"][0])

    def test_dashboard_analytics_and_report_are_sanitized(self) -> None:
        self.append_turn("secret prompt", "secret response", ["bash tools/helpers/check.sh"])
        self.append_token_count(500, cached=300, output=20)
        monitor = self.monitor()

        snapshot = monitor.snapshot()
        report = monitor.generated_report("current")

        self.assertEqual(snapshot["analytics"]["unique_helpers"], 1)
        self.assertIn("other", snapshot["analytics"]["category_costs"])
        self.assertEqual(snapshot["analytics"]["turn_diagnostics"][0]["tool_calls"], 1)
        self.assertEqual(snapshot["analytics"]["turn_diagnostics"][0]["tool_names"], ["function_call"])
        self.assertNotIn("secret prompt", report["content"])
        self.assertNotIn("secret response", report["content"])
        self.assertEqual(report["scope"], "current")

        sensitive = monitor.generated_report("current", True)
        content = monitor.content_snapshot()
        self.assertIn("secret prompt", sensitive["content"])
        self.assertIn("secret response", sensitive["content"])
        self.assertIn("tools/helpers/check.sh", sensitive["content"])
        self.assertIn("**Tool calls**", sensitive["content"])
        self.assertIn("`function_call`", sensitive["content"])
        self.assertIn(snapshot["session"]["id"], sensitive["filename"])
        self.assertTrue(sensitive["filename"].endswith("-sensitive.md"))
        self.assertTrue(sensitive["filename"].endswith(".md"))
        self.assertEqual(content["turns"][0]["commands"], ["bash tools/helpers/check.sh"])
        self.assertEqual(content["turns"][0]["tool_calls"][0]["name"], "function_call")
        self.assertIn("tools/helpers/check.sh", content["turns"][0]["tool_calls"][0]["arguments"])

    def test_codex_turn_duration_and_ttft_use_event_timestamps(self) -> None:
        self.write_event({"type": "event_msg", "timestamp": "2026-08-12T12:00:00Z", "payload": {"type": "task_started"}})
        self.write_event({"type": "response_item", "timestamp": "2026-08-12T12:00:02Z", "payload": {
            "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Working."}],
        }})
        self.write_event({"type": "event_msg", "timestamp": "2026-08-12T12:00:05Z", "payload": {"type": "task_complete"}})

        state = self.parser().update()

        self.assertEqual(state.turns[0]["ttft_ms"], 2000)
        self.assertEqual(state.turns[0]["duration_ms"], 5000)

    def test_background_start_reuses_server_and_stop_ends_it(self) -> None:
        state_root = self.root / "background-state"
        environment = dict(__import__("os").environ)
        environment["SESSION_MONITOR_STATE_ROOT"] = str(state_root)
        base = [
            sys.executable,
            str(MODULE_PATH),
            "--rollout",
            str(self.rollout),
        ]

        started = subprocess.run(
            [*base, "start", "--no-open"],
            cwd=TOOLS_ROOT.parents[3],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.addCleanup(lambda: subprocess.run(
            [*base, "stop"],
            cwd=TOOLS_ROOT.parents[3],
            env=environment,
            capture_output=True,
            timeout=10,
        ))
        reused = subprocess.run(
            [*base, "start", "--no-open"],
            cwd=TOOLS_ROOT.parents[3],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        stopped = subprocess.run(
            [*base, "stop"],
            cwd=TOOLS_ROOT.parents[3],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("started:", started.stdout)
        self.assertEqual(reused.returncode, 0, reused.stderr)
        self.assertIn("already running:", reused.stdout)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertIn("stopped.", stopped.stdout)
        self.assertFalse((state_root / "server.json").exists())

    def test_claude_adapter_normalizes_turns_tokens_tools_and_children(self) -> None:
        primary = self.root / "claude-primary.jsonl"
        child_dir = self.root / "claude-primary" / "subagents"
        child_dir.mkdir(parents=True)
        child = child_dir / "agent-child.jsonl"

        def record(type_: str, content, **extra):
            payload = {
                "type": type_,
                "sessionId": "claude-primary",
                "timestamp": "2026-08-12T12:00:00Z",
                "message": {"content": content},
                **extra,
            }
            return json.dumps(payload)

        primary.write_text("\n".join([
            record("user", [{"type": "text", "text": "Build the portable tool."}], promptId="p1"),
            record("assistant", [{"type": "tool_use", "input": {"command": "bash tools/helpers/check.sh"}}], message={
                "content": [{"type": "tool_use", "input": {"command": "bash tools/helpers/check.sh"}}],
                "usage": {"input_tokens": 100, "cache_read_input_tokens": 40, "output_tokens": 10},
                "stop_reason": None,
            }),
            record("assistant", [{"type": "text", "text": "Done."}], message={
                "content": [{"type": "text", "text": "Done."}],
                "usage": {"input_tokens": 20, "output_tokens": 5},
                "stop_reason": "end_turn",
            }),
            record("user", [{"type": "text", "text": "Continue the next slice."}], promptId="p2"),
        ]) + "\n", encoding="utf-8")
        child.write_text(record(
            "user",
            [{"type": "text", "text": "Inspect this."}],
            promptId="c1",
            agentId="child",
            isSidechain=True,
        ) + "\n", encoding="utf-8")

        config = {
            "_base": str(TOOLS_ROOT),
            "category_config": str(mod.DEFAULT_CATEGORY_CONFIG.resolve()),
            "helper_path_prefixes": ["tools/helpers/"],
            "state_root": str(self.root / "claude-state"),
            "labels": {"project": "ExampleProject"},
        }
        snapshot = mod.SessionMonitor(
            self.root,
            rollout=primary,
            agent="claude",
            project_config=config,
        ).snapshot()

        self.assertEqual(snapshot["source"]["agent"], "claude")
        self.assertEqual(snapshot["session"]["completed_turns"], 1)
        self.assertTrue(snapshot["session"]["turn_in_progress"])
        self.assertEqual(snapshot["helpers"]["invocations"], {"check.sh": 1})
        self.assertEqual(snapshot["tokens"]["session"]["total_tokens"], 175)
        self.assertIsNone(snapshot["tokens"]["session"]["reasoning_output_tokens"])
        self.assertIsNone(snapshot["tokens"]["context"]["window_tokens"])
        self.assertEqual(snapshot["subagents"]["active"], 1)

    def test_non_triplematch_project_config_controls_policy_and_handoff(self) -> None:
        category_path = self.root / "categories.json"
        category_path.write_text(json.dumps({
            "categories": [{"name": "delivery", "include": ["ship"]}],
            "fallback_category": "misc",
        }), encoding="utf-8")
        self.append_turn("Ship the release.", commands=["bash custom/helpers/release.sh"])
        state_root = self.root / "custom-state"
        config = {
            "_base": str(self.root),
            "category_config": "categories.json",
            "helper_path_prefixes": ["custom/helpers/"],
            "thresholds": {
                "turns": 1,
                "categories": 9,
                "phases": 9,
                "helper_coverage": 0.0,
                "helper_min_turns": 9,
                "context_ratio": 1.0,
            },
            "state_root": "custom-state",
            "labels": {"project": "OtherGame"},
            "continuation": {
                "mode": "Mode: Delivery",
                "system": "Project: OtherGame",
                "goal": "Continue OtherGame delivery.",
            },
        }
        monitor = mod.SessionMonitor(self.root, rollout=self.rollout, project_config=config)
        snapshot = monitor.snapshot()
        handoff = monitor.continuation_prompt({})["prompt"]

        self.assertEqual(snapshot["source"]["project"], "OtherGame")
        self.assertEqual(snapshot["categories"], {"delivery": 1})
        self.assertEqual(snapshot["helpers"]["invocations"], {"release.sh": 1})
        self.assertEqual(snapshot["warning"]["thresholds"]["turns"], 1)
        self.assertFalse(snapshot["warning"]["thresholds_overridden"])
        self.assertTrue(state_root.exists())
        self.assertIn("Mode: Delivery", handoff)
        self.assertIn("Goal: Continue OtherGame delivery.", handoff)

    def test_omitted_project_label_derives_current_git_repository(self) -> None:
        self.append_turn("Build the monitor.")
        config = {
            "_base": str(TOOLS_ROOT),
            "category_config": str(mod.DEFAULT_CATEGORY_CONFIG.resolve()),
            "helper_path_prefixes": ["tools/"],
            "state_root": str(self.root / "derived-state"),
            "labels": {},
        }

        snapshot = mod.SessionMonitor(
            self.root,
            rollout=self.rollout,
            project_config=config,
        ).snapshot()

        self.assertEqual(snapshot["source"]["project"], mod.repository_name())

    def test_gemini_adapter_normalizes_turns_tools_tokens_and_unavailable_capabilities(self) -> None:
        session = self.root / "chats" / "session-gemini.json"
        session.parent.mkdir()
        session.write_text(json.dumps({
            "sessionId": "gemini-primary",
            "startTime": "2026-08-12T12:00:00Z",
            "messages": [
                {"type": "user", "content": "Build the portable adapter."},
                {
                    "type": "gemini",
                    "content": "Done.",
                    "tokens": {"input": 100, "cached": 40, "output": 20, "thoughts": 5, "total": 120},
                    "toolCalls": [{"id": "t1", "name": "shell", "args": {"command": "bash tools/helpers/check.sh"}}],
                },
                {"type": "user", "content": "Continue."},
            ],
        }), encoding="utf-8")
        config = {
            "_base": str(TOOLS_ROOT),
            "category_config": str(mod.DEFAULT_CATEGORY_CONFIG.resolve()),
            "helper_path_prefixes": ["tools/helpers/"],
            "state_root": str(self.root / "gemini-state"),
            "labels": {"project": "ExampleProject"},
        }

        snapshot = mod.SessionMonitor(
            self.root,
            rollout=session,
            agent="gemini",
            project_config=config,
        ).snapshot()

        self.assertEqual(snapshot["source"]["agent"], "gemini")
        self.assertEqual(snapshot["session"]["completed_turns"], 1)
        self.assertTrue(snapshot["session"]["turn_in_progress"])
        self.assertEqual(snapshot["helpers"]["invocations"], {"check.sh": 1})
        self.assertEqual(snapshot["tokens"]["session"]["total_tokens"], 120)
        self.assertEqual(snapshot["tokens"]["session"]["reasoning_output_tokens"], 5)
        self.assertIsNone(snapshot["tokens"]["context"]["window_tokens"])
        self.assertFalse(snapshot["subagents"]["available"])

    def test_junie_adapter_normalizes_completed_and_active_tasks(self) -> None:
        session_dir = self.root / "session-junie"
        session_dir.mkdir()
        events = session_dir / "events.jsonl"
        records = [
            {"kind": "UserPromptEvent", "presentablePrompt": "Implement the adapter."},
            {"kind": "SessionA2uxEvent", "event": {"state": "IN_PROGRESS", "agentEvent": {
                "kind": "TerminalBlockUpdatedEvent", "stepId": "s1", "command": "bash tools/helpers/check.sh",
            }}},
            {"kind": "SessionA2uxEvent", "event": {"state": "IN_PROGRESS", "agentEvent": {
                "kind": "LlmResponseMetadataEvent", "modelUsage": [{
                    "inputTokens": 60, "cacheInputTokens": 30, "cacheCreateTokens": 10, "outputTokens": 20,
                }],
            }}},
            {"kind": "SessionA2uxEvent", "event": {"state": "IN_PROGRESS", "agentEvent": {
                "kind": "ResultBlockUpdatedEvent", "stepId": "s2", "result": "Done.",
            }}},
            {"kind": "TaskState", "state": "COMPLETED"},
            {"kind": "UserPromptEvent", "presentablePrompt": "Continue."},
        ]
        events.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
        config = {
            "_base": str(TOOLS_ROOT),
            "category_config": str(mod.DEFAULT_CATEGORY_CONFIG.resolve()),
            "helper_path_prefixes": ["tools/helpers/"],
            "state_root": str(self.root / "junie-state"),
            "labels": {"project": "ExampleProject"},
        }

        snapshot = mod.SessionMonitor(
            self.root,
            rollout=events,
            agent="junie",
            project_config=config,
        ).snapshot()

        self.assertEqual(snapshot["source"]["agent"], "junie")
        self.assertEqual(snapshot["session"]["completed_turns"], 1)
        self.assertTrue(snapshot["session"]["turn_in_progress"])
        self.assertEqual(snapshot["helpers"]["invocations"], {"check.sh": 1})
        self.assertEqual(snapshot["tokens"]["session"]["total_tokens"], 120)
        self.assertIsNone(snapshot["tokens"]["session"]["reasoning_output_tokens"])
        self.assertIsNone(snapshot["tokens"]["context"]["window_tokens"])
        self.assertFalse(snapshot["subagents"]["available"])


if __name__ == "__main__":
    unittest.main()
