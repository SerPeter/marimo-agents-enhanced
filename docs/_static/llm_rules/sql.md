# Marimo Rules — SQL

## DuckDB Integration

- Use marimo's SQL cells with `mo.sql()` for DuckDB queries
- The result is automatically assigned to a DataFrame variable
- You can reference Python DataFrames directly in SQL queries by name
- Don't add comments in cells that use `mo.sql()`

## Syntax

```python
# Default DuckDB engine
df = mo.sql(f"""
    SELECT * FROM my_table WHERE location = 'Seattle';
""")

# With a specific SQL engine
df = mo.sql(f"""
    SELECT * FROM my_table LIMIT 100;
""", engine=engine)
```

## Tips

- Python DataFrames (polars, pandas) are automatically available as tables in DuckDB
- Use f-strings for parameterized queries, but be careful with SQL injection if using user input
- The returned DataFrame can be used in subsequent Python cells

## Examples

<example title="SQL with DuckDB">
```
@app.cell
def _():
    import marimo as mo
    import polars as pl
    return

@app.cell
def _():
    weather = pl.read_csv('https://raw.githubusercontent.com/vega/vega-datasets/refs/heads/main/data/weather.csv')
    return

@app.cell
def _():
    seattle_weather_df = mo.sql(
        f"""
        SELECT * FROM weather WHERE location = 'Seattle';
        """
    )
    return
```
</example>
