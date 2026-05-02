from rich.console import Console
from rich.table import Table
import json

console = Console()

def print_error(msg: str):
    console.print(f"[red]Error:[/red] {msg}")

def print_success(msg: str):
    console.print(f"[green]Success:[/green] {msg}")

def print_table(title: str, columns: list, rows: list, format_json: bool = False):
    if format_json:
        # Convert rows to dicts based on columns
        data = []
        for row in rows:
            data.append(dict(zip(columns, row)))
        console.print_json(json.dumps(data))
        return

    table = Table(title=title)
    for col in columns:
        table.add_column(col)

    for row in rows:
        table.add_row(*[str(item) for item in row])

    console.print(table)

def print_json(data: dict):
    console.print_json(json.dumps(data))
