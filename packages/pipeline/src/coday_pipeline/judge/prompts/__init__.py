from importlib.resources import files

INSTRUCTIONS = files(__name__).joinpath("instructions.md").read_text(encoding="utf-8")
