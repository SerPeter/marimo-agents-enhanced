# Marimo Rules — Visualization

## General

- Include proper labels, titles, and color schemes
- Make visualizations interactive where appropriate
- The visualization object must be the last expression in the cell to be displayed

## Matplotlib

- Use `plt.gca()` as the last expression instead of `plt.show()`
- For more control, create figure and axes explicitly:
  ```python
  fig, ax = plt.subplots()
  ax.plot(x, y)
  ax
  ```

## Plotly

- Return the figure object directly as the last expression
- For reactive selections, wrap with `mo.ui.plotly(fig)` — this creates a UI element whose `.value` contains the selected data points

## Altair

- Return the chart object directly as the last expression
- Add tooltips where appropriate
- You can pass polars DataFrames directly to Altair
- For reactive selections, wrap with `mo.ui.altairweather_chart(chart)` — this creates a UI element whose `.value` contains the selected data

## Examples

<example title="Interactive chart with Altair">
```
@app.cell
def _():
    import marimo as mo
    import altair as alt
    import polars as pl
    return

@app.cell
def _():
    weather = pl.read_csv("https://raw.githubusercontent.com/vega/vega-datasets/refs/heads/main/data/weather.csv")
    weather_dates = weather.with_columns(
        pl.col("date").str.strptime(pl.Date, format="%Y-%m-%d")
    )
    weather_chart = (
        alt.Chart(weather_dates)
        .mark_point()
        .encode(
            x="date:T",
            y="temp_max",
            color="location",
        )
    )
    return

@app.cell
def _():
    chart = mo.ui.altairweather_chart(weather_chart)
    chart
    return

@app.cell
def _():
    chart.value
    return
```
</example>
