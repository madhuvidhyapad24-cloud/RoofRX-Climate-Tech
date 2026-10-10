"""Crop one image per building from an aerial GeoTIFF using GeoJSON footprints.

    python classifier/prep_crops.py --tif scene.tif --footprints buildings.geojson --out data/crops

If a footprint has a property named by --label-field (default 'roof_material')
with one of metal/concrete/tile/other, the crop goes to out/<label>/ ; otherwise
to out/unlabeled/ (hand-label those into folders, then run train_classifier.py).

Needs: rasterio, geopandas, pillow, numpy  (not installed in the build sandbox -
this script has NOT been run; test it on your machine).
"""
import argparse
import os

import geopandas as gpd
import numpy as np
import rasterio
from PIL import Image
from rasterio.mask import mask

LABELS = {"metal", "concrete", "tile", "other"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tif", required=True)
    ap.add_argument("--footprints", required=True)
    ap.add_argument("--out", default="data/crops")
    ap.add_argument("--label-field", default="roof_material")
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--max", type=int, default=5000)
    a = ap.parse_args()

    with rasterio.open(a.tif) as src:
        gdf = gpd.read_file(a.footprints).to_crs(src.crs)
        n = 0
        for i, row in gdf.iterrows():
            if n >= a.max:
                break
            try:
                arr, _ = mask(src, [row.geometry], crop=True, filled=True)
            except Exception:
                continue  # footprint outside the scene
            if arr.shape[0] < 3 or arr.shape[1] < 4 or arr.shape[2] < 4:
                continue
            img = np.moveaxis(arr[:3], 0, -1).astype(np.uint8)
            label = str(row.get(a.label_field, "")).lower()
            folder = label if label in LABELS else "unlabeled"
            os.makedirs(os.path.join(a.out, folder), exist_ok=True)
            Image.fromarray(img).resize((a.size, a.size)).save(
                os.path.join(a.out, folder, f"{i}.png"))
            n += 1
    print(f"wrote {n} crops to {a.out}")


if __name__ == "__main__":
    main()
