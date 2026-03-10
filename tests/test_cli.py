import unittest

from plot2svg.cli import build_parser


class CliTest(unittest.TestCase):
    def test_cli_accepts_execution_profile_argument(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--input", "picture/F2.png", "--output", "outputs/F2", "--profile", "quality"])
        self.assertEqual(args.profile, "quality")


if __name__ == "__main__":
    unittest.main()
