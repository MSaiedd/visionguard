export interface Region {
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  peak_score: number;
  area_fraction: number;
}
export interface Inspection {
  id: string;
  filename: string;
  batch: string;
  width: number;
  height: number;
  state: string;
  created_at: number;
  score: number | null;
  threshold: number | null;
  decision: string | null;
  regions: Region[];
  latency_ms: number | null;
  model_version: string | null;
  error: string;
  review: string;
  review_note: string;
  reviewed_by: string | null;
  revision: number;
}
export interface Model {
  version: string;
  method: string;
  backbone: string;
  dimensions: number;
  input_size: number[];
  image_threshold: number;
  pixel_threshold: number;
  fitted_normal_images: number;
  score_definition: string;
  weights_sha256: string;
  license: string;
  dataset: string;
}
export interface Workspace {
  name: string;
  identity: { user: string; role: string; auth_mode: string };
  model: { ready: boolean; error: string; metadata: Model | null };
  stats: {
    images: number;
    complete: number;
    queued: number;
    suspect: number;
    reviewed: number;
    pending_review: number;
    mean_latency_ms: number | null;
  };
  batches: string[];
}
export interface Metrics {
  images: number;
  positive_images: number;
  auroc: number;
  average_precision: number;
  precision: number;
  recall: number;
  f1: number;
  confusion: {
    true_negative: number;
    false_positive: number;
    false_negative: number;
    true_positive: number;
  };
}
export interface Evaluation {
  available: boolean;
  model: Model;
  train_images: number;
  fitted_normal_images: number;
  validation: Metrics;
  test: Metrics;
  pixel_test_auroc: number;
  pixel_test_average_precision: number;
  pixel_evaluation: string;
  latency_ms: {
    mean: number;
    p95: number;
    batch_size: number;
    includes: string;
  };
  elapsed_seconds: number;
  limits: string;
}
