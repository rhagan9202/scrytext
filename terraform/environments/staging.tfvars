# Terraform variables for staging environment
# Reduced capacity and cost optimization

aws_region  = "us-east-1"
environment = "staging"

# VPC Configuration
vpc_cidr = "10.1.0.0/16"
private_subnet_cidrs = [
  "10.1.1.0/24",
  "10.1.2.0/24",
  "10.1.3.0/24"
]
public_subnet_cidrs = [
  "10.1.101.0/24",
  "10.1.102.0/24",
  "10.1.103.0/24"
]
database_subnet_cidrs = [
  "10.1.201.0/24",
  "10.1.202.0/24",
  "10.1.203.0/24"
]

# EKS Configuration
eks_cluster_version = "1.28"
eks_node_groups = {
  general = {
    instance_types = ["t3.medium"]  # Smaller for staging
    min_size       = 1
    max_size       = 3
    desired_size   = 2
  }
  workers = {
    instance_types = ["t3.medium"]  # Smaller for staging
    min_size       = 1
    max_size       = 5
    desired_size   = 2
  }
}

# RDS Configuration
rds_instance_class    = "db.t3.small"  # Smaller for staging
rds_allocated_storage = 50  # Reduced from 100GB
rds_max_allocated_storage = 100  # Reduced max
rds_backup_retention_period = 7  # Shorter retention
rds_multi_az = false  # Single AZ for cost savings

# ElastiCache Redis Configuration
redis_node_type = "cache.t3.micro"  # Smallest instance
redis_num_cache_nodes = 1  # Single node for staging
redis_automatic_failover_enabled = false  # Disabled for cost

# MSK Kafka Configuration
kafka_instance_type = "kafka.t3.small"  # Smaller for staging
kafka_ebs_volume_size = 100  # Reduced from 500GB
kafka_number_of_broker_nodes = 2  # Reduced for staging

# Tagging
tags = {
  Environment = "staging"
  Project     = "scry-ingestor"
  ManagedBy   = "terraform"
  CostCenter  = "engineering"
}
