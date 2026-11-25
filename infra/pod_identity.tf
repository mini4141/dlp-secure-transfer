# Least-privilege roles for the two workloads, assumed through EKS Pod Identity (no static keys).

data "aws_iam_policy_document" "pods_assume" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

locals {
  workloads = {
    api = {
      statements = [
        {
          actions   = ["s3:PutObject", "s3:GetObject"]
          resources = ["${aws_s3_bucket.transfers.arn}/*"]
        },
        {
          actions   = ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"]
          resources = [aws_sqs_queue.scan.arn]
        },
        {
          actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
          resources = [aws_kms_key.main.arn]
        },
      ]
    }
    worker = {
      statements = [
        {
          actions   = ["s3:GetObject", "s3:PutObject"]
          resources = ["${aws_s3_bucket.transfers.arn}/*"]
        },
        {
          actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"]
          resources = [aws_sqs_queue.scan.arn]
        },
        {
          actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
          resources = [aws_kms_key.main.arn]
        },
      ]
    }
  }
}

data "aws_iam_policy_document" "workload" {
  for_each = local.workloads
  dynamic "statement" {
    for_each = each.value.statements
    content {
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }
}

resource "aws_iam_role" "workload" {
  for_each           = local.workloads
  name               = "${var.name}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.pods_assume.json
}

resource "aws_iam_role_policy" "workload" {
  for_each = local.workloads
  name     = "access"
  role     = aws_iam_role.workload[each.key].id
  policy   = data.aws_iam_policy_document.workload[each.key].json
}

# ServiceAccount names are created by the Helm chart: <release>-api / <release>-worker.
resource "aws_eks_pod_identity_association" "workload" {
  for_each        = local.workloads
  cluster_name    = aws_eks_cluster.main.name
  namespace       = var.k8s_namespace
  service_account = "${var.name}-${each.key}"
  role_arn        = aws_iam_role.workload[each.key].arn
  depends_on      = [aws_eks_addon.pod_identity]
}
