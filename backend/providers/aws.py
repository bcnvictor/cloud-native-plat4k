"""
AWS Cloud Provider implementation using boto3.
"""
import asyncio
from typing import List, Dict, Any
from backend.providers.base import CloudProvider
from shared.models import ResourceCreate
from backend.core.exceptions import CloudProviderException

class AWSProvider(CloudProvider):
    def __init__(self, credentials: Dict[str, str]):
        super().__init__(credentials)
        import boto3
        self.ec2 = boto3.client(
            'ec2',
            aws_access_key_id=self.credentials.get('aws_access_key_id'),
            aws_secret_access_key=self.credentials.get('aws_secret_access_key'),
            region_name=self.credentials.get('region', 'us-east-1')
        )

    async def list_instances(self) -> List[Dict[str, Any]]:
        # In a real async environment we might use aiobotocore
        # Here we run sync boto3 in thread pool if needed, or simply block (for student project)
        try:
            response = self.ec2.describe_instances()
            instances = []
            for reservation in response.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instances.append({
                        "external_id": instance.get('InstanceId'),
                        "status": instance.get('State', {}).get('Name'),
                        "metadata": {
                            "instance_type": instance.get('InstanceType'),
                            "private_ip": instance.get('PrivateIpAddress')
                        }
                    })
            return instances
        except Exception as e:
            raise CloudProviderException(f"AWS Error: {str(e)}")

    async def create_instance(self, payload: ResourceCreate) -> Dict[str, Any]:
        try:
            # We would need an AMI id, using a default Amazon Linux 2 AMI for us-east-1 as example
            response = self.ec2.run_instances(
                ImageId='ami-0c55b159cbfafe1f0', # Note: this AMI might be outdated, but serves as example
                InstanceType=payload.size or 't2.micro',
                MinCount=1,
                MaxCount=1
            )
            instance = response['Instances'][0]
            return {
                "external_id": instance['InstanceId'],
                "status": "pending",
                "metadata": {"instance_type": instance['InstanceType']}
            }
        except Exception as e:
            raise CloudProviderException(f"AWS Error: {str(e)}")

    async def delete_instance(self, external_id: str) -> bool:
        try:
            self.ec2.terminate_instances(InstanceIds=[external_id])
            return True
        except Exception as e:
            raise CloudProviderException(f"AWS Error: {str(e)}")

    async def get_instance(self, external_id: str) -> Dict[str, Any]:
        try:
            response = self.ec2.describe_instances(InstanceIds=[external_id])
            instance = response['Reservations'][0]['Instances'][0]
            return {"external_id": external_id, "status": instance['State']['Name']}
        except Exception as e:
             raise CloudProviderException(f"AWS Error: {str(e)}")

    async def list_storage(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.1)
        return []

    async def create_storage(self, payload: ResourceCreate) -> Dict[str, Any]:
        try:
            response = self.ec2.create_volume(
                AvailabilityZone=self.credentials.get('region', 'us-east-1') + 'a',
                Size=int(payload.size or 10),
                VolumeType='gp2'
            )
            return {"external_id": response['VolumeId'], "status": response['State'], "metadata": {"size": response['Size']}}
        except Exception as e:
             raise CloudProviderException(f"AWS Error: {str(e)}")

    async def delete_storage(self, external_id: str) -> bool:
        try:
            self.ec2.delete_volume(VolumeId=external_id)
            return True
        except Exception as e:
             raise CloudProviderException(f"AWS Error: {str(e)}")

    async def list_networks(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.1)
        return []

    async def get_network_status(self, external_id: str) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        return {"external_id": external_id, "status": "available"}
