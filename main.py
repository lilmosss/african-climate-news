import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
import json
import re

# -------------------------------
# App Title
# -------------------------------
st.title("African Climate Articles Analysis")
st.text("This dataset analyzes how African countries and their major news organizations have reported on climate change between 2020 and 2024. The data was collected from Media Cloud collections, which track online news articles from local and regional media outlets.")
st.header("Reports")


COUNTRY_ALIASES = {
    # Sudan
    "south sudan": "s. sudan",
    
    # Djibouti
    "republic of djibouti": "djibouti",
    "Djibouti.": "djibouti",

    "Eq.Guinea: eq"


    # Congo
    "dem. rep. congo": "dem. rep. congo",
    "democratic republic of the congo": "dem. rep. congo",

    # Central Africa
    "central african republic": "central african rep.",

    # Côte d'Ivoire
    "côte d'ivoire": "ivory coast",
    "cote d'ivoire": "ivory coast",

    # Guinea variants
    "eq guinea": "equatorial guinea",
    "equatorial guinea": "equatorial guinea",

    # Gambia
    "the gambia": "gambia",

    # Islands
    "sao tome and principe": "são tomé and príncipe",
    "são tomé and principe": "são tomé and príncipe",

    # Cabo Verde
    "cape verde": "cabo verde",

    # Eswatini
    "swaziland": "eswatini"
}
def clean_country(name):
    if pd.isna(name):
        return None

    name = (
        str(name)
        .lower()
        .replace("\u00a0", " ")
        .strip()
    )

    return COUNTRY_ALIASES.get(name, name)



# -------------------------------
# Load and combine CSV files
# -------------------------------
 

@st.cache_data
def load_and_combine_data(base_path="AfricanArticles"):
    all_data = []

    for csv_file_path in Path(base_path).rglob("*.csv"):
        df = pd.read_csv(csv_file_path)

        # Extract Country from filename
        stem_parts = csv_file_path.stem.split("_")
        df["Country"] = stem_parts[0].strip().title()

        # Extract 4-digit year from filename
        match = re.search(r"\b(\d{4})\b", csv_file_path.stem)
        df["Year"] = match.group(1) if match else csv_file_path.parent.name

        # Convert date_published if exists
        if "date_published" in df.columns:
            df["date_published"] = pd.to_datetime(df["date_published"], errors="coerce")

        all_data.append(df)

    return pd.concat(all_data, ignore_index=True)

# Load dataset
df = load_and_combine_data("AfricanArticles")
df["Year"] = df["Year"].astype(str)

# -------------------------------
# Year Selection
# -------------------------------

available_years_int = available_years_int = sorted(
    [
        int(match.group(1))
        for y in df["Year"].unique()
        if (match := re.search(r"\b(\d{4})\b", str(y)))
    ]
)

st.markdown("### Select Year")
selected_year = st.slider(
    "",
    min_value=min(available_years_int),
    max_value=max(available_years_int),
    value=min(available_years_int),
    step=1
)

# Filter dataframe for the selected year
df_year = df[df["Year"].str.contains(str(selected_year))]



# -------------------------------
# Aggregate Articles per Country
# -------------------------------
df_gb_year_country = df_year.groupby("Country").agg(
    total_articles=("url", "count")
).reset_index()

# Clean country names for merging
df_gb_year_country["Country_clean"] = df_gb_year_country["Country"].apply(clean_country)


# -------------------------------
# Load GDP and Population
# -------------------------------
df_meta = pd.read_csv("africa_gdp_population.csv")
# Clean country names in metadata
df_meta["Country_clean"] = df_meta["Country"].apply(clean_country)


# Remove extra spaces
df_meta.columns = df_meta.columns.str.strip()

# Rename to standard columns
rename_dict = {}
for col in df_meta.columns:
    if "Population" in col:
        rename_dict[col] = "Population"
    if "GDP" in col:
        rename_dict[col] = "GDP"
df_meta.rename(columns=rename_dict, inplace=True)

# -------------------------------
# Convert to numeric and fix units
# -------------------------------
df_meta["Population"] = pd.to_numeric(df_meta["Population"].astype(str).str.replace(",", "").str.strip(), errors="coerce")
df_meta["GDP"] = pd.to_numeric(df_meta["GDP"].astype(str).str.replace(",", "").str.strip(), errors="coerce")

# Convert population in thousands to actual numbers if needed
if df_meta["Population"].max() < 1_000_000:
    df_meta["Population"] = df_meta["Population"] * 1000

def normalize_country(name):
    return (
        name.strip()
            .lower()
            .replace("&", "and")
            .replace("-", " ")
    )

# Merge with article counts
df_map = df_gb_year_country.merge(
    df_meta,
    on="Country_clean",
    how="left"
)


# -------------------------------
# Load GeoJSON
# -------------------------------
with open("africa_countries.geo.json") as f:
    geo = json.load(f)

# Ensure all countries are included for the map
geo_names = [feature["properties"]["name"] for feature in geo["features"]]
df_geo = pd.DataFrame({"Country": geo_names})

# Clean GeoJSON country names
df_geo["Country_clean"] = df_geo["Country"].apply(clean_country)

df_map_full = df_geo.merge(
    df_map,
    on="Country_clean",
    how="left"
)


# Fill missing values

df_map_full["total_articles"] = df_map_full["total_articles"].fillna(0)


# -------------------------------
# Normalize Article Counts
# -------------------------------
df_map_full["articles_per_million_people"] = (
    df_map_full["total_articles"] /
    (df_map_full["Population"] / 1_000_000)
)
df_map_full["articles_per_billion_gdp"] = (
    df_map_full["total_articles"] /
    (df_map_full["GDP"])
)


# -------------------------------
# Plot Choropleth Map
# -------------------------------
st.subheader(f"Climate Coverage Map for {selected_year}")
st.text("Geographic coverage: All recognized African countries represented in the Media Cloud dataset \nContent source: National and regional online news articles\nMetrics included:\nTotal articles per country – the number of climate-related articles published\nArticles per million people – normalizes coverage relative to population size\nArticles relative to GDP – highlights coverage compared to the country’s economic size")


# Dropdown to choose metric
metric = st.selectbox("Select metric for map:", 
                      ["Raw Articles", "Articles per Million People", "Articles per Billion GDP"])
z_col = {
    "Raw Articles": "total_articles",
    "Articles per Million People": "articles_per_million_people",
    "Articles per Billion GDP": "articles_per_billion_gdp"
}[metric]

hover_text = df_map_full.apply(
    lambda row: f"{row['Country']}<br>"
                f"Articles: {int(row['total_articles'])}<br>"
                f"Population: {row['Population']/1_000_000:.1f}M<br>"
                f"GDP:${row['GDP']:.1f}B<br>"
                f"{metric}: {row[z_col]:.2f}", axis=1
)

fig = go.Figure(
    go.Choroplethmapbox(
        geojson=geo,
        locations=df_map_full.Country,
        featureidkey="properties.name",
        z=df_map_full[z_col],
        colorscale="Viridis",
        marker_opacity=0.7,
        marker_line_width=0.5,
        colorbar_title=metric,
        text=hover_text,
        hoverinfo="text"
    )
)

fig.update_layout(
    mapbox_style="carto-positron",
    mapbox_zoom=2.5,
    mapbox_center={"lat": 0, "lon": 20},
    width=1000,
    height=650,
    margin={"r":0,"t":0,"l":0,"b":0}
)

st.plotly_chart(fig)

# -------------------------------
# Time Series Data
# -------------------------------

st.subheader("Climate Coverage Over Time by Country")
st.text("This time series reveals which countries are more actively covering climate change and identify trends over time in media coverage")

countries = sorted(df["Country"].unique())
selected_country = st.selectbox("Select a country:", countries)
df["Year_int"] = (
    df["Year"]
    .astype(str)
    .str.extract(r"(\d{4})")[0]
    .astype(int)
)
df_country_time = (
    df[df["Country"] == selected_country]
    .groupby("Year_int")
    .agg(total_articles=("url", "count"))
    .reset_index()
)

fig_country = go.Figure()

fig_country.add_trace(
    go.Scatter(
        x=df_country_time["Year_int"],
        y=df_country_time["total_articles"],
        mode="lines+markers",
        name=selected_country
    )
)

fig_country.update_layout(
    xaxis_title="Year",
    yaxis_title="Number of Climate Articles",
    template="plotly_white"
)

st.plotly_chart(fig_country, use_container_width=True)

