variable "region" {
  type    = string
  default = "ap-southeast-2"
}

variable "aws_profile" {
  type        = string
  default     = "dlp-secure-transfer-deployer"
  description = "The only AWS CLI profile this project may use."
}

variable "name" {
  type    = string
  default = "dlp-secure-transfer"
}

variable "k8s_namespace" {
  type    = string
  default = "dlp"
}

variable "cluster_version" {
  type    = string
  default = "1.36"
}

variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "node_count" {
  type    = number
  default = 2
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}
