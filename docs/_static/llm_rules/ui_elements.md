# Marimo Rules — UI Elements

## Key Principles

- Access UI element values with `.value` attribute (e.g., `slider.value`)
- **Create UI elements in one cell and reference `.value` in later cells** — you cannot read `.value` in the same cell where the element is defined
- Prefer reactive updates over callbacks (marimo handles reactivity automatically)
- Group related UI elements for better organization using `mo.hstack()`, `mo.vstack()`, `mo.tabs()`

## Available UI elements

- `mo.ui.altair_chart(altair_chart)` — interactive Altair chart with selection
- `mo.ui.button(value=None, kind='primary')` — clickable button
- `mo.ui.run_button(label=None, tooltip=None, kind='primary')` — button that triggers cell execution
- `mo.ui.checkbox(label='', value=False)` — boolean checkbox
- `mo.ui.date(value=None, label=None, full_width=False)` — date picker
- `mo.ui.dropdown(options, value=None, label=None, full_width=False)` — dropdown selector
- `mo.ui.file(label='', multiple=False, full_width=False)` — file upload
- `mo.ui.number(value=None, label=None, full_width=False)` — number input
- `mo.ui.radio(options, value=None, label=None, full_width=False)` — radio button group
- `mo.ui.refresh(options: List[str], default_interval: str)` — auto-refresh timer
- `mo.ui.slider(start, stop, value=None, label=None, full_width=False, step=None)` — numeric slider
- `mo.ui.range_slider(start, stop, value=None, label=None, full_width=False, step=None)` — range slider
- `mo.ui.table(data, columns=None, on_select=None, sortable=True, filterable=True)` — interactive table
- `mo.ui.text(value='', label=None, full_width=False)` — text input
- `mo.ui.text_area(value='', label=None, full_width=False)` — multiline text input
- `mo.ui.data_explorer(df)` — interactive data explorer
- `mo.ui.dataframe(df)` — DataFrame viewer with transformations
- `mo.ui.plotly(plotly_figure)` — interactive Plotly chart with selection
- `mo.ui.tabs(elements: dict[str, mo.ui.Element])` — tabbed interface
- `mo.ui.array(elements: list[mo.ui.Element])` — array of UI elements
- `mo.ui.form(element: mo.ui.Element, label='', bordered=True)` — form wrapper (submits on button click)

## Patterns

### Conditional execution with `mo.stop` and `run_button`

```python
# Cell 1: define UI
run = mo.ui.run_button(label="Execute")
run

# Cell 2: gate execution
mo.stop(not run.value, mo.md("Click the button to run"))
# ... expensive computation here ...
```

### Multiple UI elements

```python
# Cell 1: define controls
species = mo.ui.dropdown(options=["All", "Setosa", "Versicolor"], value="All", label="Species")
x_axis = mo.ui.dropdown(options=numeric_columns, value="SepalLength", label="X")
y_axis = mo.ui.dropdown(options=numeric_columns, value="SepalWidth", label="Y")
mo.hstack([species, x_axis, y_axis])

# Cell 2: use values
filtered = df if species.value == "All" else df.filter(pl.col("Species") == species.value)
```

## Examples

<example title="Basic UI with reactivity">
```
@app.cell
def _():
    import marimo as mo
    import altair as alt
    import polars as pl
    import numpy as np
    return

@app.cell
def _():
    n_points = mo.ui.slider(10, 100, value=50, label="Number of points")
    n_points
    return

@app.cell
def _():
    x = np.random.rand(n_points.value)
    y = np.random.rand(n_points.value)
    df = pl.DataFrame({"x": x, "y": y})
    chart = alt.Chart(df).mark_circle(opacity=0.7).encode(
        x=alt.X('x', title='X axis'),
        y=alt.Y('y', title='Y axis')
    ).properties(
        title=f"Scatter plot with {n_points.value} points",
        width=400,
        height=300
    )
    chart
    return
```
</example>

<example title="Run Button">
```
@app.cell
def _():
    import marimo as mo
    return

@app.cell
def _():
    first_button = mo.ui.run_button(label="Option 1")
    second_button = mo.ui.run_button(label="Option 2")
    [first_button, second_button]
    return

@app.cell
def _():
    if first_button.value:
        mo.md("You chose option 1!")
    elif second_button.value:
        mo.md("You chose option 2!")
    else:
        mo.md("Click a button!")
    return
```
</example>
