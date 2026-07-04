"""PyInstaller entry point (SPEC §18.2).

Kept intentionally minimal: all real startup logic lives in koekichi.app so
the frozen app and `uv run koekichi` behave identically (SPEC §18.6).
"""

from koekichi.app import main

if __name__ == "__main__":
    main()
