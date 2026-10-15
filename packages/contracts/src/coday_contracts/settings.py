from pydantic import BaseModel, Field


class ReviewSettings(BaseModel):
    automatic: bool = True
    instructions: str = Field(default="", max_length=12000)
    exclude_patterns: list[str] = Field(
        default_factory=lambda: [
            "**/node_modules/**",
            "**/vendor/**",
            "**/dist/**",
            "**/build/**",
            "**/generated/**",
            "**/*.min.js",
            "**/*.map",
            "**/*.lock",
            "**/package-lock.json",
            "**/pnpm-lock.yaml",
            "**/yarn.lock",
            "**/bun.lockb",
        ],
        max_length=100,
    )
