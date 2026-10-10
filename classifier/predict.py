"""Predict roof material for crops and merge into a buildings CSV.

    python classifier/predict.py --model results/classifier.pt --crops data/crops/unlabeled \
        --buildings buildings_no_material.csv --out buildings.csv

Crop filenames must be '<building_id>.png'. The input CSV needs every column
RoofRx requires except 'material'. Not run in the build sandbox (needs torch).
"""
import argparse
import glob
import os

import pandas as pd
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--crops", required=True)
    ap.add_argument("--buildings", required=True)
    ap.add_argument("--out", default="buildings.csv")
    a = ap.parse_args()

    ck = torch.load(a.model, map_location="cpu")
    classes = ck["classes"]
    m = models.resnet18(weights=None)
    m.fc = nn.Linear(m.fc.in_features, len(classes))
    m.load_state_dict(ck["state_dict"])
    m.eval()
    tf = transforms.Compose([transforms.Resize((128, 128)), transforms.ToTensor(),
                             transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    pred = {}
    with torch.no_grad():
        for p in glob.glob(os.path.join(a.crops, "*.png")):
            bid = int(os.path.splitext(os.path.basename(p))[0])
            pred[bid] = classes[m(tf(Image.open(p).convert("RGB")).unsqueeze(0)).argmax(1).item()]
    df = pd.read_csv(a.buildings)
    df["material"] = df["building_id"].map(pred).fillna("other")
    df.to_csv(a.out, index=False)
    print(f"predicted {len(pred)} / {len(df)} buildings -> {a.out} (unmatched set to 'other')")


if __name__ == "__main__":
    main()
