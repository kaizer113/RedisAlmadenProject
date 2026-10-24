# Redis Cloud Pro with AWS VPC peering

## Archived benchmark project

The experiment is complete and its Flex database, VPC peering, and EC2 test VM have been removed. The existing AWS VPC is retained. See [Flex loader and benchmarks](flex-benchmark/README.md), [measured results](flex-benchmark/results/report.md), and [CSV export](flex-benchmark/results/benchmark-results.csv). The Terraform below describes the earlier 25 GB experiment; it does not recreate the 1 TB Flex deployment.

Adapted from https://github.com/kaizer113/RedisCloudWithAWSTransitGateway.

Creates a Redis Cloud Pro subscription and a 25 GB dataset database in AWS us-west-2, sized for 25,000 operations/sec with replication disabled. Direct VPC peering replaces the Transit Gateway, RAM share, attachments, and TGW routes. Public Redis access is enabled for laptop testing; database source IPs are restricted to the consumer VPC and the laptop public /32 configured in terraform.tfvars. Persistence defaults to none, matching the reference demo. Password authentication is enabled; TLS is disabled by default as in the reference.

Terraform creates the Redis-side peering request, accepts it in AWS, and adds a route to the Redis deployment CIDR in each consumer VPC route table. Redis Cloud manages the return route. Existing VPCs and subnets are read, not owned by this stack. Redis-managed cloud accounts reject infrastructure `resource_tags`; these cannot be set on the subscription cloud resources. The database and AWS peering connection receive `owner=lionel_giavelli` and `skip_deletion=yes`.

## Selected AWS network

- AWS account: `735486936198`
- VPC: `vpc-0bdba995c15e5371d` (`myredis1-test-vpc`), `10.0.0.0/16`
- Redis deployment: `192.168.0.0/24`, non-overlapping with the selected VPC
- Suggested subnet for a later CLI-created EC2 test host: `subnet-0a5769ac32b192dad`, `10.0.1.0/24`, us-west-2a
- Public subnet route table: `rtb-04a459be3490a4503`, with an existing internet gateway route

No EC2 instance is created by this project. Later, use an EC2 security group with outbound access to Redis and Session Manager for administration; the public subnet requires a public IP for internet-based SSM access unless VPC endpoints are added. The existing private subnets currently have no internet/NAT route.

## Run

Use your existing AWS CLI credential chain. Optionally set `aws_profile` in `terraform.tfvars`.
Set `REDISCLOUD_ACCESS_KEY` and `REDISCLOUD_SECRET_KEY` in the environment. A local `.env`, when present, is ignored by Git and should have mode 600.

```sh
source .env
terraform init
terraform fmt -check
terraform validate
terraform plan -out=deployment.tfplan
terraform apply deployment.tfplan
terraform output
```

The selected VPC is configured in local `terraform.tfvars`. For another deployment, copy `terraform.tfvars.example`, choose a non-overlapping Redis /24, and verify the target VPC routes. Account protection is set in the AWS provider; change it deliberately if deploying elsewhere. `aws_region` and `redis_region` must match for this example.

Billing defaults to the account's credit-card payment method. Set `payment_method = "marketplace"` for Marketplace billing or `null` for a direct contract, as appropriate for the target account.

```sh
terraform output -raw database_password
terraform output -raw private_endpoint
```

Terraform state and saved plans contain the database password. Keep them private and out of source control. Preserve the local state to manage or destroy the created resources.

## Cleanup

```sh
source .env
terraform plan -destroy
terraform destroy
```

This deletes the database, subscription, peering and routes created here. It does not delete the existing VPC or subnets. `skip_deletion=yes` is an external cleanup label; it does not prevent explicit Terraform destruction.

Provider references:
- https://registry.terraform.io/providers/RedisLabs/rediscloud/latest/docs/resources/rediscloud_subscription
- https://registry.terraform.io/providers/RedisLabs/rediscloud/latest/docs/resources/rediscloud_subscription_database
- https://registry.terraform.io/providers/RedisLabs/rediscloud/latest/docs/resources/rediscloud_subscription_peering

## Deployed resources (2026-10-23)

- Subscription: `3460170`
- Database: `14714560` (`redis-peering-db`)
- Private endpoint: `copacetic-covetable-quotable-15743.db.redis.io:10231`
- Endpoint resolved to `192.168.0.106` during verification.
- Peering: `pcx-07a9ece85b80edbee` (active)
- All three consumer VPC route tables have an active route for `192.168.0.0/24` through the peering.
- Redis API verified: active database, 25 GB dataset, replication false, 25,000 operations/sec.
- Post-deployment Terraform plan: no changes.
- VPC peering data-path testing remains pending until an EC2 test host is launched. Laptop testing uses the public endpoint.

## Laptop memory benchmark

See [benchmark/README.md](benchmark/README.md). Public access remains enabled as requested; update the allowed /32 if the laptop public IP changes.
