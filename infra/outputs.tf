output "region" {
  value = var.region
}

output "cluster_name" {
  value = aws_eks_cluster.main.name
}

output "ecr_api" {
  value = aws_ecr_repository.repo["api"].repository_url
}

output "ecr_worker" {
  value = aws_ecr_repository.repo["worker"].repository_url
}

output "bucket" {
  value = aws_s3_bucket.transfers.bucket
}

output "queue_name" {
  value = aws_sqs_queue.scan.name
}

output "queue_url" {
  value = aws_sqs_queue.scan.url
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.url
}

output "kms_key_arn" {
  value = aws_kms_key.main.arn
}

output "kms_key_id" {
  value = aws_kms_key.main.key_id
}

output "rds_address" {
  value = aws_db_instance.main.address
}

output "db_password" {
  value     = random_password.db.result
  sensitive = true
}

output "log_group" {
  value = aws_cloudwatch_log_group.eks.name
}
