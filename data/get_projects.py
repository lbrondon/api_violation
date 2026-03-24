import pandas as pd
import sys
from pathlib import Path


def get_projects(csv_path: str, column_name: str = "Project") -> list:
    """
    Reads a CSV file and returns a sorted list of unique projects.

    Args:
        csv_path (str): Path to the CSV file.
        column_name (str): Name of the column containing project names.

    Returns:
        list: Sorted list of unique projects.
    """
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    if column_name not in df.columns:
        raise ValueError(
            f"Column '{column_name}' not found. Available columns: {list(df.columns)}"
        )

    projects = (
        df[column_name]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    return sorted(projects)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_projects.py <csv_path>")
        sys.exit(1)

    csv_path = sys.argv[1]
    projects = get_projects(csv_path)

    print(f"Total projects: {len(projects)}")
    for p in projects:
        print(p)
