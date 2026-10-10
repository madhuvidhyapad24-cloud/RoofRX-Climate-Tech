"""Fine-tune a small CNN on labelled roof crops.

Expected folders (torchvision ImageFolder layout):
    data/crops_split/train/<class>/*.png
    data/crops_split/val/<class>/*.png      <- hold out a different AREA if you can

    python classifier/train_classifier.py --data data/crops_split --epochs 8

Writes results/classifier.pt and results/classifier_report.json (accuracy +
confusion matrix). Report THESE numbers, and say which area was held out.

Needs torch + torchvision (not installed in the build sandbox - this script has
NOT been run; test it on your machine / Colab).
"""
import argparse
import json
import os

import torch
import torch.nn as nn
from torchvision import datasets, models, transforms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--no-pretrained", action="store_true", help="skip ImageNet weights (no download)")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    tr = transforms.Compose([transforms.Resize((128, 128)), transforms.RandomHorizontalFlip(),
                             transforms.RandomVerticalFlip(), transforms.ToTensor(), norm])
    va = transforms.Compose([transforms.Resize((128, 128)), transforms.ToTensor(), norm])
    train = datasets.ImageFolder(os.path.join(a.data, "train"), tr)
    val = datasets.ImageFolder(os.path.join(a.data, "val"), va)
    classes = train.classes
    tl = torch.utils.data.DataLoader(train, a.batch, shuffle=True)
    vl = torch.utils.data.DataLoader(val, a.batch)

    weights = None if a.no_pretrained else models.ResNet18_Weights.DEFAULT
    model = models.resnet18(weights=weights)
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    model.to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr)
    loss_fn = nn.CrossEntropyLoss()

    for ep in range(a.epochs):
        model.train()
        for x, y in tl:
            x, y = x.to(dev), y.to(dev)
            opt.zero_grad()
            loss_fn(model(x), y).backward()
            opt.step()
        print(f"epoch {ep + 1}/{a.epochs} done")

    model.eval()
    cm = [[0] * len(classes) for _ in classes]
    with torch.no_grad():
        for x, y in vl:
            pred = model(x.to(dev)).argmax(1).cpu()
            for t, p in zip(y.tolist(), pred.tolist()):
                cm[t][p] += 1
    total = sum(map(sum, cm))
    acc = sum(cm[i][i] for i in range(len(classes))) / max(total, 1)
    print(f"validation accuracy: {acc:.3f} on {total} crops")

    os.makedirs(a.out, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": classes}, os.path.join(a.out, "classifier.pt"))
    with open(os.path.join(a.out, "classifier_report.json"), "w") as f:
        json.dump({"val_accuracy": acc, "n_val": total, "classes": classes,
                   "confusion_matrix_rows_true_cols_pred": cm}, f, indent=2)


if __name__ == "__main__":
    main()
