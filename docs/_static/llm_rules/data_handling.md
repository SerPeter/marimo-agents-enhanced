# Marimo Rules — Data Handling

## General Principles

- Use polars for data manipulation (preferred over pandas)
- Implement proper data validation
- Handle missing values appropriately
- Use efficient data structures
- A variable in the last expression of a cell is automatically displayed as a table

## Polars Patterns

```python
# Read data
df = pl.read_csv("data.csv")
df = pl.read_parquet("data.parquet")

# Filter
filtered = df.filter(pl.col("age") > 30)

# Select and transform
result = df.select(
    pl.col("name"),
    pl.col("age").cast(pl.Float64),
    (pl.col("score") * 100).alias("score_pct"),
)

# Group and aggregate
summary = df.group_by("category").agg(
    pl.col("value").mean().alias("avg_value"),
    pl.col("value").count().alias("count"),
)
```

## Data Explorer

Use `mo.ui.data_explorer(df)` for interactive exploration of DataFrames:

```python
@app.cell
def _():
    cars_df = pl.DataFrame(data.cars())
    mo.ui.data_explorer(cars_df)
    return
```

## Large Data

- For large datasets, prefer lazy evaluation with `pl.scan_csv()` / `pl.scan_parquet()`
- Use `.collect()` only when you need the results
- Filter early to reduce data size before visualization
- Use `mo.ui.table()` for paginated display of large DataFrames
