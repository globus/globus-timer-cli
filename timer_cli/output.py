import json
from typing import List

import click
import requests


def make_table(headers: List[str], rows: List[List[str]]) -> str:
    contents = [headers] + rows
    widths = [max(len(cell) for cell in col) for col in zip(*contents)]
    formatted_header = " | ".join(
        cell.ljust(width) for cell, width in zip(headers, widths)
    )
    formatted_rows = [
        " | ".join(cell.ljust(width) for cell, width in zip(row, widths))
        for row in rows
    ]
    max_row_width = len(formatted_header)
    if formatted_rows:
        max_row_width = max(max_row_width, max(map(len, formatted_rows)))
    separator = "-|-".join("-" * w for w in widths)
    formatted_rows_block = "\n".join(formatted_rows)
    return f"{formatted_header}\n{separator}\n{formatted_rows_block}"


def show_response(response: requests.Response):
    if response.status_code >= 400:
        click.echo(f"got response code {response.status_code}", err=True)
    click.echo(json.dumps(response.json(), indent=2))
