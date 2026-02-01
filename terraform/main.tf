# Scry_Ingestor Infrastructure - Main Configuration
# Provisions EKS cluster, RDS, MSK Kafka, Redis, and networking

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
  }
  
  backend "s3" {
    bucket         = "scry-terraform-state"
    key            = "scry-ingestor/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "scry-ingestor"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Local variables
locals {
  name_prefix = "scry-${var.environment}"
  
  common_tags = {
    Project     = "scry-ingestor"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ============================================================================
# VPC and Networking
# ============================================================================
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  
  name = "${local.name_prefix}-vpc"
  cidr = var.vpc_cidr
  
  azs              = data.aws_availability_zones.available.names
  private_subnets  = var.private_subnet_cidrs
  public_subnets   = var.public_subnet_cidrs
  database_subnets = var.database_subnet_cidrs
  
  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "production"
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  # VPC Flow Logs
  enable_flow_log                      = true
  create_flow_log_cloudwatch_iam_role  = true
  create_flow_log_cloudwatch_log_group = true
  
  tags = local.common_tags
}

# ============================================================================
# EKS Cluster
# ============================================================================
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"
  
  cluster_name    = "${local.name_prefix}-eks"
  cluster_version = var.eks_cluster_version
  
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true
  
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
  
  # Cluster addons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }
  
  # Node groups
  eks_managed_node_groups = {
    general = {
      name = "${local.name_prefix}-general"
      
      instance_types = ["t3.large"]
      capacity_type  = "ON_DEMAND"
      
      min_size     = var.environment == "production" ? 3 : 2
      max_size     = var.environment == "production" ? 10 : 5
      desired_size = var.environment == "production" ? 3 : 2
      
      labels = {
        role = "general"
      }
    }
    
    workers = {
      name = "${local.name_prefix}-workers"
      
      instance_types = ["t3.xlarge"]
      capacity_type  = "SPOT"
      
      min_size     = 2
      max_size     = 20
      desired_size = 3
      
      labels = {
        role = "worker"
        workload = "data-processing"
      }
      
      taints = [{
        key    = "workload"
        value  = "data-processing"
        effect = "NoSchedule"
      }]
    }
  }
  
  # Cluster security group
  cluster_security_group_additional_rules = {
    ingress_nodes_ephemeral_ports_tcp = {
      description                = "Nodes on ephemeral ports"
      protocol                   = "tcp"
      from_port                  = 1025
      to_port                    = 65535
      type                       = "ingress"
      source_node_security_group = true
    }
  }
  
  tags = local.common_tags
}

# ============================================================================
# RDS PostgreSQL
# ============================================================================
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"
  
  identifier = "${local.name_prefix}-postgres"
  
  engine               = "postgres"
  engine_version       = "15.4"
  family               = "postgres15"
  major_engine_version = "15"
  instance_class       = var.rds_instance_class
  
  allocated_storage     = var.rds_allocated_storage
  max_allocated_storage = var.rds_max_allocated_storage
  storage_encrypted     = true
  
  db_name  = "scry_ingestor"
  username = "scry"
  port     = 5432
  
  multi_az               = var.environment == "production"
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.rds.id]
  
  # Backups
  backup_retention_period = var.environment == "production" ? 30 : 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"
  
  # Enhanced monitoring
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  create_cloudwatch_log_group     = true
  
  # Performance Insights
  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  
  # Deletion protection
  deletion_protection      = var.environment == "production"
  skip_final_snapshot     = var.environment != "production"
  final_snapshot_identifier_prefix = "${local.name_prefix}-final"
  
  tags = local.common_tags
}

# RDS Security Group
resource "aws_security_group" "rds" {
  name_prefix = "${local.name_prefix}-rds-"
  vpc_id      = module.vpc.vpc_id
  description = "Security group for RDS PostgreSQL"
  
  ingress {
    description     = "PostgreSQL from EKS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = merge(local.common_tags, { Name = "${local.name_prefix}-rds-sg" })
}

# ============================================================================
# ElastiCache Redis
# ============================================================================
module "redis" {
  source  = "terraform-aws-modules/elasticache/aws"
  version = "~> 1.0"
  
  cluster_id               = "${local.name_prefix}-redis"
  engine_version           = "7.0"
  node_type                = var.redis_node_type
  num_cache_nodes          = var.environment == "production" ? 2 : 1
  parameter_group_family   = "redis7"
  port                     = 6379
  
  subnet_ids             = module.vpc.private_subnets
  vpc_id                 = module.vpc.vpc_id
  security_group_ids     = [aws_security_group.redis.id]
  
  # At-rest encryption
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  
  # Automatic backups
  snapshot_retention_limit = var.environment == "production" ? 7 : 1
  snapshot_window          = "03:00-05:00"
  
  # Maintenance
  maintenance_window = "sun:05:00-sun:06:00"
  
  # Auto minor version upgrade
  auto_minor_version_upgrade = true
  
  tags = local.common_tags
}

# Redis Security Group
resource "aws_security_group" "redis" {
  name_prefix = "${local.name_prefix}-redis-"
  vpc_id      = module.vpc.vpc_id
  description = "Security group for ElastiCache Redis"
  
  ingress {
    description     = "Redis from EKS"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = merge(local.common_tags, { Name = "${local.name_prefix}-redis-sg" })
}

# ============================================================================
# MSK Kafka Cluster
# ============================================================================
resource "aws_msk_cluster" "kafka" {
  cluster_name           = "${local.name_prefix}-kafka"
  kafka_version          = "3.5.1"
  number_of_broker_nodes = var.environment == "production" ? 3 : 2
  
  broker_node_group_info {
    instance_type  = var.kafka_instance_type
    client_subnets = module.vpc.private_subnets
    storage_info {
      ebs_storage_info {
        volume_size = var.kafka_volume_size
      }
    }
    security_groups = [aws_security_group.kafka.id]
  }
  
  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
    encryption_at_rest_kms_key_arn = aws_kms_key.kafka.arn
  }
  
  configuration_info {
    arn      = aws_msk_configuration.kafka.arn
    revision = aws_msk_configuration.kafka.latest_revision
  }
  
  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.kafka.name
      }
    }
  }
  
  tags = local.common_tags
}

# Kafka Configuration
resource "aws_msk_configuration" "kafka" {
  name              = "${local.name_prefix}-kafka-config"
  kafka_versions    = ["3.5.1"]
  server_properties = <<-EOT
    auto.create.topics.enable=true
    default.replication.factor=2
    min.insync.replicas=2
    num.io.threads=8
    num.network.threads=5
    num.partitions=3
    num.replica.fetchers=2
    replica.lag.time.max.ms=30000
    socket.receive.buffer.bytes=102400
    socket.request.max.bytes=104857600
    socket.send.buffer.bytes=102400
    unclean.leader.election.enable=false
  EOT
}

# Kafka KMS Key
resource "aws_kms_key" "kafka" {
  description             = "KMS key for ${local.name_prefix} Kafka encryption"
  deletion_window_in_days = 10
  tags                    = local.common_tags
}

# Kafka CloudWatch Log Group
resource "aws_cloudwatch_log_group" "kafka" {
  name              = "/aws/msk/${local.name_prefix}-kafka"
  retention_in_days = var.environment == "production" ? 30 : 7
  tags              = local.common_tags
}

# Kafka Security Group
resource "aws_security_group" "kafka" {
  name_prefix = "${local.name_prefix}-kafka-"
  vpc_id      = module.vpc.vpc_id
  description = "Security group for MSK Kafka"
  
  ingress {
    description     = "Kafka from EKS"
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  
  ingress {
    description     = "Kafka TLS from EKS"
    from_port       = 9094
    to_port         = 9094
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = merge(local.common_tags, { Name = "${local.name_prefix}-kafka-sg" })
}

# ============================================================================
# Data Sources
# ============================================================================
data "aws_availability_zones" "available" {
  state = "available"
}

# ============================================================================
# Outputs
# ============================================================================
output "eks_cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "rds_endpoint" {
  description = "RDS endpoint"
  value       = module.rds.db_instance_endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "Redis endpoint"
  value       = module.redis.primary_endpoint_address
  sensitive   = true
}

output "kafka_bootstrap_brokers" {
  description = "Kafka bootstrap brokers"
  value       = aws_msk_cluster.kafka.bootstrap_brokers_tls
  sensitive   = true
}
