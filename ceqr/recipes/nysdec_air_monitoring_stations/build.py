from ceqr.helper.engines import recipe_engine, edm_engine, ceqr_engine
from ceqr.helper.config_loader import load_config
from ceqr.helper.exporter import exporter
import pandas as pd
from pathlib import Path
import numpy as np
import geopandas as gpd
import os

def get_borocode(c):
    borocode = {
        "New York": 1,
        "Bronx": 2,
        "Kings": 3,
        "Queens": 4,
        "Richmond": 5
    }
    return borocode.get(c, '')

if __name__ == "__main__":
    # Load configuration
    config = load_config(Path(__file__).parent/'config.json')
    input_table = config['inputs'][0]
    output_table = config['outputs'][0]['output_table']
    DDL = config['outputs'][0]['DDL']

    # import data
    df = gpd.GeoDataFrame.from_postgis(f'''SELECT *, wkb_geometry AS geom FROM {input_table}
                                                            WHERE region = '2';''', 
                                                        con=recipe_engine, geom_col='geom')
    df['borocode'] = df.county.apply(lambda x: get_borocode(x))
    

    os.system('echo "exporting table ..."')
    # export table to EDM_DATA
    exporter(df=df,
             output_table=output_table,
             DDL=DDL,
             sep='~',
             geo_column='geom')