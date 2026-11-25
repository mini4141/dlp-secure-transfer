data "aws_caller_identity" "current" {}

resource "aws_kms_key" "main" {
  description             = "${var.name} data key (S3, SQS, RDS)"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "main" {
  name          = "alias/${var.name}"
  target_key_id = aws_kms_key.main.key_id
}

resource "aws_s3_bucket" "transfers" {
  bucket        = "${var.name}-${data.aws_caller_identity.current.account_id}-${var.region}"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "transfers" {
  bucket = aws_s3_bucket.transfers.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "transfers" {
  bucket = aws_s3_bucket.transfers.id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "transfers" {
  bucket                  = aws_s3_bucket.transfers.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Browsers PUT files straight to S3 with presigned URLs.
resource "aws_s3_bucket_cors_configuration" "transfers" {
  bucket = aws_s3_bucket.transfers.id
  cors_rule {
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = ["*"]
    allowed_headers = ["*"]
    max_age_seconds = 300
  }
}

data "aws_iam_policy_document" "bucket_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.transfers.arn, "${aws_s3_bucket.transfers.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "transfers" {
  bucket     = aws_s3_bucket.transfers.id
  policy     = data.aws_iam_policy_document.bucket_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.transfers]
}

resource "aws_sqs_queue" "dlq" {
  name              = "${var.name}-scan-dlq"
  kms_master_key_id = aws_kms_key.main.arn
}

resource "aws_sqs_queue" "scan" {
  name                       = "${var.name}-scan"
  kms_master_key_id          = aws_kms_key.main.arn
  visibility_timeout_seconds = 30
  receive_wait_time_seconds  = 10
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_ecr_repository" "repo" {
  for_each             = toset(["api", "worker"])
  name                 = "${var.name}/${each.key}"
  force_delete         = true
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}
