# VisionGuard surface reference model

**Task:** one-class surface anomaly detection and localization. It detects unusual appearance relative to
normal reference images; it does not recognize named defect categories or certify an item safe.

## Components and fitting

- Frozen ImageNet-pretrained ResNet18 IMAGENET1K_V1, features from layers 1/2/3 (448 channels combined).
- Input resized to 320 high × 128 wide; ImageNet RGB normalization.
- Fixed-seed selection of 48 feature channels; per-position mean and full covariance.
- Covariance receives 0.05 diagonal regularization before inversion.
- Mahalanobis distances are bilinearly upsampled and Gaussian-smoothed (sigma 3).
- Image score is the 99.5th percentile of the map. Pixel components over a separate threshold produce boxes;
  components below eight resized pixels are ignored. At most 30 regions are shown.
- Image and localization thresholds maximize validation F1 independently. A ±10% image-threshold band is
  shown as “borderline · review”; this is an operational margin, not calibrated uncertainty.

The neural backbone is not gradient fine-tuned. Fitting learns normal-reference Gaussian statistics.
Reference and validation choices are recorded in source and in the artifact's report.

## Dataset and evaluation

KolektorSDD2, original official archive. A duplicate copy of 10301.png and its mask is excluded only after
byte equality with the originals is confirmed. The remaining set has 2,331 official training and 1,004
official test images. The official training set is stratified with seed 42 into 1,865 train / 466 validation.
The fitted reference uses 1,000 normal training images. Positive training images do not enter reference fitting.
Test images are not used for threshold selection. Exact image duplicates after copy exclusion: zero.
Physical-item IDs are unavailable; exact deduplication cannot establish physical-item independence.

The official test run has AUROC 0.937960, average precision 0.812732, 83 true positives, 866 true negatives,
28 false positives and 27 false negatives. Pixel AUROC is 0.972973 on a fixed stride-4 sample of resized masks;
this is not a full-resolution pixel benchmark. Full split IDs and test scores appear in reports/evaluation.json.

## Intended use and limits

Noncommercial research/portfolio inspection of this surface family and capture setup, with human review.
New product types, camera alignment, resolution or lighting need their own reference and evaluation.
The model can miss real defects (27 in the recorded test) and flag normal texture. Image/region scores are
not probabilities. A clear score is not an assurance of product safety or a substitute for a qualified inspector.

The normal-reference artifact has CC BY-NC-SA 4.0 reference-data terms; see DATA_LICENSE.md. The training checkpoint uses
safetensors. Serving uses a checksum-verified ONNX graph and allow_pickle=False NumPy statistics, and model
version strings include the serving-artifact digest. The export is checked against recorded PyTorch predictions. Human feedback
is persisted separately; retraining is a deliberate offline operation, followed by reevaluation and restart.
