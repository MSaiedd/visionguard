# Dataset, reference artifact and screenshot attribution

Kolektor Surface-Defect Dataset 2 (KolektorSDD2 / KSDD2).
Images and annotations were provided by **Kolektor Group d.o.o.** and released by **ViCoS Lab,
University of Ljubljana**, associated with Jakob Božič, Domen Tabernik and Danijel Skočaj.

Primary source: https://www.vicos.si/resources/kolektorsdd2/
Original archive: https://data.vicos.si/datasets/KSDD/KolektorSDD2.zip
License: **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International**.
License text: https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en
The dataset owner requests contact with Danijel Skočaj for commercial use.

```bibtex
@article{Bozic2021COMIND,
  author = {Bozic, Jakob and Tabernik, Domen and Skocaj, Danijel},
  journal = {Computers in Industry},
  title = {Mixed supervision for surface-defect detection: from weakly to fully supervised learning},
  year = {2021}
}
```

Changes made here: images are resized and normalized for model fitting, normalized to oriented PNG
for app intake, shown with generated heatmaps and derived region boxes, and used to fit normal-patch
statistics. Example images are selected deterministically: the first six positive and first six negative
images by filename from the official test partition. They are examples, not an additional test set.
The browser walkthrough additionally uses test image 20100.png. No example is chosen to hide a benchmark error.

Dataset-derived samples, model statistics and dataset portions of screenshots keep CC BY-NC-SA 4.0 terms.
The release artifact is distributed under those noncommercial reference-use terms. Application source code
and original deterministic test images are MIT; those terms do not override rights in third-party material.
The frozen backbone is torchvision ResNet18 IMAGENET1K_V1; source and pretrained weights retain upstream terms:
https://github.com/pytorch/vision and https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html

This repository does not claim affiliation with Kolektor or ViCoS, or commercial approval for this benchmark.
