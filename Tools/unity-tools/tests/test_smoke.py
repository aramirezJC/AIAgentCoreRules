"""Smoke tests: every script starts from this folder, and codeindex / usages answer on a tiny
synthetic Unity project (ProjectVersion.txt + one generated-style .csproj). typecheck and
unitysource need an installed Unity editor, so only their --help is covered here."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = ["codeindex.py", "usages.py", "typecheck.py", "unitysource.py"]

CSPROJ = """<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <DefineConstants>UNITY_EDITOR</DefineConstants>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="Assets\\Scripts\\Thing.cs" />
    <Compile Include="Assets\\Scripts\\Caller.cs" />
  </ItemGroup>
</Project>
"""

THING = """namespace Demo
{
    public interface IThing
    {
        void Run();
    }

    public class Thing : IThing
    {
        public void Run()
        {
        }
    }
}
"""

CALLER = """namespace Demo
{
    public class Caller
    {
        private readonly IThing _thing = new Thing();

        public void Go()
        {
            _thing.Run();
        }
    }
}
"""


def run(script, *args):
    return subprocess.run([sys.executable, str(TOOL_DIR / script), *args],
                          capture_output=True, text=True, timeout=120)


class HelpTests(unittest.TestCase):
    def test_every_script_starts(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                result = run(script, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)


class FakeProjectTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="unity-tools-test-"))
        (self.root / "ProjectSettings").mkdir()
        (self.root / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.10f1\n")
        scripts = self.root / "Assets" / "Scripts"
        scripts.mkdir(parents=True)
        (scripts / "Thing.cs").write_text(THING)
        (scripts / "Caller.cs").write_text(CALLER)
        (self.root / "Assembly-CSharp.csproj").write_text(CSPROJ)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_codeindex_finds_implementer(self):
        result = run("codeindex.py", "--project", str(self.root), "implementers", "IThing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Thing", result.stdout)
        self.assertTrue((self.root / "Library" / "codeindex.sqlite").is_file())

    def test_usages_finds_member_call(self):
        result = run("usages.py", "--project", str(self.root), "IThing", "--members", "Run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Caller.cs", result.stdout)


if __name__ == "__main__":
    unittest.main()
