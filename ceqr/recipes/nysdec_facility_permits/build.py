from ceqr.helper.engines import recipe_engine, edm_engine, ceqr_engine
from ceqr.helper.config_loader import load_config
from ceqr.helper.exporter import exporter
from ceqr.helper.geocode import get_hnum, get_sname, g, GeosupportError, create_geom
from multiprocessing import Pool, cpu_count
from shapely.wkt import loads, dumps
import pandas as pd
import geopandas as gpd
from pathlib import Path
import numpy as np
import os

def geocode(inputs):
    hnum = inputs.get('housenum', '')
    sname = inputs.get('streetname', '')
    zip_code = inputs.get('zipcode', '')

    hnum = str('' if hnum is None else hnum)
    sname = str('' if sname is None else sname)
    zip_code = str('' if zip_code is None else zip_code)

    try:
        geo = g['1B'](street_name=sname, house_number=hnum, zip_code=zip_code)
        geo = parser(geo)
        geo.update(inputs)
        return geo
    except GeosupportError:
        try:
            geo = g['AP'](street_name=sname, house_number=hnum, zip_code=zip_code)
            geo = parser(geo)
            geo.update(inputs)
            return geo
        except GeosupportError as e:
            geo = parser(e.result)
            geo.update(inputs)
            return geo

def parser(geo):
    return dict(
        geo_housenum = geo.get('House Number - Display Format', ''),
        geo_streetname = geo.get('First Street Name Normalized', ''),
        geo_bbl = geo.get('BOROUGH BLOCK LOT (BBL)', {}).get('BOROUGH BLOCK LOT (BBL)', '',),
        geo_bin = geo.get('Building Identification Number (BIN) of Input Address or NAP', ''),
        geo_latitude = geo.get('Latitude', ''),
        geo_longitude = geo.get('Longitude', ''),
        geo_grc = geo.get('Geosupport Return Code (GRC)', ''),
    )

def clean_address(x):
    if x != None:
        sep = ['|', '&', '@', ' AND ']
        for i in sep:
            x = x.split(i, maxsplit=1)[0]
    return x

if __name__ == "__main__":
    # Load configuration
    config = load_config(Path(__file__).parent/'config.json')
    input_table_state = config['inputs'][0]
    input_table_title_v = config['inputs'][1]
    output_table = config['outputs'][0]['output_table']
    DDL = config['outputs'][0]['DDL']
    output_table2 = config['outputs'][1]['output_table']
    DDL2 = config['outputs'][1]['DDL']

    # import data
    dec_state_facility_permits = pd.read_sql(f'''SELECT *, 'State' AS source FROM {input_table_state}''', con=recipe_engine)
    dec_title_v_facility_permits = pd.read_sql(f'''SELECT *, 'Title V' AS source FROM {input_table_title_v}''', con=recipe_engine)

    dec_title_v_facility_permits.columns = dec_state_facility_permits.columns

    df = dec_state_facility_permits.append(dec_title_v_facility_permits)

    # geocoding ... with 1E
    df.rename(columns={"facility_zip": "zipcode", "expire_date": "expiration_date"}, inplace=True)
    df['address'] = df['facility_location'].apply(lambda x: clean_address(x))
    df['housenum'] = df['address'].apply(get_hnum)\
                                  .apply(lambda x: x.split('/',maxsplit=1)[0] if x != None else x)
    df['streetname'] = df['address'].apply(get_sname)
    records = df.to_dict('records')

    # Multiprocess
    with Pool(processes=cpu_count()) as pool:
        it = pool.map(geocode, records, 10000)

    df = pd.DataFrame(it)
    df = df[df['geo_grc'] != '71']
    df['geo_address'] = None
    df['geo_longitude'] = pd.to_numeric(df['geo_longitude'],errors='coerce')
    df['geo_latitude'] = pd.to_numeric(df['geo_latitude'],errors='coerce')
    df = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.geo_longitude, df.geo_latitude))
    df['geom'] = df['geometry'].apply(lambda x: None if np.isnan(x.xy[0]) else str(x))

    SQL = f'''
        UPDATE {output_table} SET geo_address=geo_housenum||' '||geo_streetname;

        ALTER TABLE {output_table}
        ADD COLUMN id SERIAL PRIMARY KEY;

        DELETE FROM {output_table}
        WHERE id NOT IN(
            WITH date AS(
                SELECT facility_name||address AS facility, MAX(issue_date::date) as latest_issue_date
                FROM {output_table}
                GROUP BY facility_name||address
            )
            SELECT min(id)
            FROM {output_table} p, date d
            WHERE p.facility_name||address = d.facility
            AND p.issue_date::date = d.latest_issue_date
            OR d.latest_issue_date IS NULL
            GROUP BY p.facility_name||address
        )
        OR geom IS NULL;

        ALTER TABLE {output_table} DROP COLUMN id;
        '''
    

    SQL2 = f'''
        UPDATE {output_table2} SET geo_address=geo_housenum||' '||geo_streetname;

        ALTER TABLE {output_table2}
        ADD COLUMN id SERIAL PRIMARY KEY;

        DELETE FROM {output_table2}
        WHERE id NOT IN(
            WITH date AS(
                SELECT facility_name||address AS facility, MAX(issue_date::date) as latest_issue_date
                FROM {output_table2}
                GROUP BY facility_name||address
            )
            SELECT min(id)
            FROM {output_table2} p, date d
            WHERE p.facility_name||address = d.facility
            AND p.issue_date::date = d.latest_issue_date
            OR d.latest_issue_date IS NULL
            GROUP BY p.facility_name||address
        )
        OR geom IS NOT NULL;

        ALTER TABLE {output_table2} DROP COLUMN id;
        '''

    os.system('echo "exporting table ..."')
    # export table to EDM_DATA
    exporter(df=df,
             output_table=output_table,
             DDL=DDL,
             sql=SQL,
             sep='~',
             geo_column='geom')

    exporter(df=df,
             output_table=output_table2,
             DDL=DDL2,
             sql=SQL2,
             sep='~',
             geo_column='geom')