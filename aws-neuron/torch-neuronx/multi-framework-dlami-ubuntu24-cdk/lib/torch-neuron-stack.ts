import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';
import * as fs from 'fs';
import * as path from 'path';

export interface TorchNeuronStackProps extends cdk.StackProps {
  instanceType: string;
  useCapacityBlock: boolean;
  capacityReservationId: string;
  subnetId: string;
  volumeSize: number;
}

interface Config {
  regions: {
    [key: string]: {
      amiSsmParameter: string;
    };
  };
  defaultVolumeSize: number;
  codeServerUser: string;
  homeFolder: string;
}

export class TorchNeuronStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: TorchNeuronStackProps) {
    super(scope, id, props);

    // 設定ファイルを読み込み
    const configPath = path.join(__dirname, '..', 'config.json');
    const config: Config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));

    const region = this.region;
    const regionConfig = config.regions[region];

    if (!regionConfig) {
      throw new Error(`Region ${region} is not configured in config.json`);
    }

    // パスワード生成
    const password = new secretsmanager.Secret(this, 'CodeServerPassword', {
      description: 'Code-server password',
      generateSecretString: {
        excludePunctuation: true,
        passwordLength: 16,
      },
    });

    // IAM Role
    const role = new iam.Role(this, 'CodeServerInstanceRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AdministratorAccess'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('CloudWatchAgentServerPolicy'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonQDeveloperAccess'),
      ],
    });

    const instanceProfile = new iam.CfnInstanceProfile(this, 'CodeServerInstanceProfile', {
      roles: [role.roleName],
    });

    // Security Group
    const securityGroup = new ec2.SecurityGroup(this, 'CodeServerSecurityGroup', {
      vpc: props.subnetId
        ? ec2.Vpc.fromLookup(this, 'VPC', { isDefault: true })
        : ec2.Vpc.fromLookup(this, 'VPC', { isDefault: true }),
      description: 'Security Group for code-server - allow all HTTP for testing',
      allowAllOutbound: true,
    });

    // Allow HTTP from anywhere for testing (TODO: restrict to CloudFront)
    securityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'Allow HTTP from anywhere'
    );

    // AMI - Deep Learning AMI Neuron Ubuntu 24.04
    // SSM Parameter Storeから最新のAMI IDを動的に取得
    const amiId = ec2.MachineImage.fromSsmParameter(
      regionConfig.amiSsmParameter,
      {
        os: ec2.OperatingSystemType.LINUX,
      }
    ).getImage(this).imageId;

    // User Data
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      `mkdir -p ${config.homeFolder}`,
      `chown -R ${config.codeServerUser}:${config.codeServerUser} ${config.homeFolder}`
    );

    // Launch Template用のプロパティを構築
    const launchTemplateData: any = {
      imageId: amiId,
      instanceType: props.instanceType,
      blockDeviceMappings: [
        {
          deviceName: '/dev/sda1',
          ebs: {
            volumeSize: props.volumeSize,
            volumeType: 'gp3',
            deleteOnTermination: true,
            encrypted: true,
          },
        },
      ],
      monitoring: {
        enabled: true,
      },
      iamInstanceProfile: {
        arn: instanceProfile.attrArn,
      },
      securityGroupIds: [securityGroup.securityGroupId],
      userData: cdk.Fn.base64(userData.render()),
      tagSpecifications: [
        {
          resourceType: 'instance',
          tags: [
            {
              key: 'Name',
              value: id,
            },
          ],
        },
      ],
    };

    // Capacity Block設定
    if (props.useCapacityBlock) {
      launchTemplateData.instanceMarketOptions = {
        marketType: 'capacity-block',
      };
    }

    if (props.capacityReservationId) {
      launchTemplateData.capacityReservationSpecification = {
        capacityReservationTarget: {
          capacityReservationId: props.capacityReservationId,
        },
      };
    }

    // Launch Template（L1 Construct）
    const launchTemplate = new ec2.CfnLaunchTemplate(this, 'CodeServerLaunchTemplate', {
      launchTemplateName: `${id}-LaunchTemplate`,
      launchTemplateData,
    });

    // Launch Templateが依存リソースの後に作成されるようにする
    launchTemplate.node.addDependency(instanceProfile);
    launchTemplate.node.addDependency(securityGroup);

    // EC2 Instance
    const instance = new ec2.CfnInstance(this, 'CodeServerInstance', {
      launchTemplate: {
        launchTemplateId: launchTemplate.ref,
        version: launchTemplate.attrLatestVersionNumber,
      },
      subnetId: props.subnetId || undefined,
      tags: [
        {
          key: 'Name',
          value: id,
        },
        {
          key: 'ManagedBy',
          value: 'CDK',
        },
        {
          key: 'CapacityBlock',
          value: props.useCapacityBlock ? 'true' : 'false',
        },
      ],
    });

    // Outputs
    new cdk.CfnOutput(this, 'InstanceId', {
      description: 'EC2 Instance ID',
      value: instance.ref,
    });

    new cdk.CfnOutput(this, 'InstancePublicDnsName', {
      description: 'EC2 Instance Public DNS Name',
      value: instance.attrPublicDnsName,
    });

    new cdk.CfnOutput(this, 'Password', {
      description: 'Code-server Password',
      value: password.secretValue.unsafeUnwrap(),
    });

    new cdk.CfnOutput(this, 'SSMConnectCommand', {
      description: 'SSM Connect Command',
      value: `aws ssm start-session --target ${instance.ref} --region ${this.region}`,
    });
  }
}
