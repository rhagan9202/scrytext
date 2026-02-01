# Terraform variables for production environment
# High availability and performance configuration

aws_region  = "us-east-1"
environment = "production"

# VPC Configuration
vpc_cidr = "10.0.0.0/16"
private_subnet_cidrs = [
  "10.0.1.0/24",
  "10.0.2.0/24",
  "10.0.3.0/24"
]
public_subnet_cidrs = [
  "10.0.101.0/24",
  "10.0.102.0/24",
  "10.0.103.0/24"
]
database_subnet_cidrs = [
  "10.0.201.0/24",
  "10.0.202.0/24",
  "10.0.203.0/24"
]

# EKS Configuration
eks_cluster_version = "1.28"
eks_node_groups = {
  general = {
    instance_types = ["t3.large"]  # Larger for production
    min_size       = 3  # Higher min for HA
    max_size       = 10
    desired_size   = 5
  }
  workers = {
    instance_types = ["t3.xlarge"]  # Larger for production
    min_size       = 3  # Higher min for HA
    max_size       = 20
    desired_size   = 5
  }
}

# RDS Configuration
rds_instance_class    = "db.r6g.xlarge"  # Production-grade instance
rds_allocated_storage = 500  # Large storage
rds_max_allocated_storage = 2000  # High max for growth
rds_backup_retention_period = 30  # 30-day retention for compliance
rds_multi_az = true  # Multi-AZ for HA

# ElastiCache Redis Configuration
redis_node_type = "cache.r6g.large"  # Production-grade instance
redis_num_cache_nodes = 3  # Multi-node cluster for HA
redis_automatic_failover_enabled = true  # Enabled for HA

# MSK Kafka Configuration
kafka_instance_type = "kafka.m5.xlarge"  # Production-grade instance
kafka_ebs_volume_size = 1000  # Large storage for production
kafka_number_of_broker_nodes = 3  # Full HA with 3 brokers

# Tagging
tags = {
  Environment = "production"
  Project     = "scry-ingestor"
  ManagedBy   = "terraform"
  CostCenter  = "engineering"
  Compliance  = "required"
  BackupPolicy = "daily"
}
