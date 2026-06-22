import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { IconEye, IconEyeOff, IconRefresh } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { gitlabApi } from '@/api/gitlab';
import { clustersApi } from '@/api/clusters';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';

export function AdminSettings() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([{ label: 'Platform', to: '/admin/clusters' }, { label: 'Settings' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const [platformName, setPlatformName] = useState('Cloud Native Platform');
  const [publicUrl, setPublicUrl] = useState('');
  const [gitlabUrl, setGitlabUrl] = useState('');
  const [gitlabGroup, setGitlabGroup] = useState('');
  const [gitlabToken, setGitlabToken] = useState('');
  const [tokenVisible, setTokenVisible] = useState(false);
  const [gitlabConnected, setGitlabConnected] = useState<boolean | null>(null);

  const [clusterName, setClusterName] = useState('');
  const [clusterEndpoint, setClusterEndpoint] = useState('');
  const [kubeconfig, setKubeconfig] = useState('');

  const [kubeconfigVisible, setKubeconfigVisible] = useState(false);

  const healthMutation = useMutation({
    mutationFn: gitlabApi.healthcheck,
    onSuccess: (data) => setGitlabConnected(data.connected),
    onError: () => setGitlabConnected(false),
  });

  const saveGitlabMutation = useMutation({
    mutationFn: () => gitlabApi.saveCredentials(gitlabToken, gitlabGroup),
    onSuccess: () => setGitlabToken(''),
  });

  const registerClusterMutation = useMutation({
    mutationFn: () =>
      clustersApi.register({
        name: clusterName,
        endpoint: clusterEndpoint,
        kubeconfig,
      }),
    onSuccess: () => {
      setClusterName('');
      setClusterEndpoint('');
      setKubeconfig('');
    },
  });

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <h1 className="text-xl font-semibold text-foreground mb-6">Platform settings</h1>
      <div className="max-w-2xl flex flex-col gap-6">

      {/* Global params */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Global settings</h2>
        <div className="flex flex-col gap-3">
          <Input
            label="Platform name"
            value={platformName}
            onChange={(e) => setPlatformName(e.target.value)}
          />
          <Input
            label="Public URL"
            value={publicUrl}
            onChange={(e) => setPublicUrl(e.target.value)}
            placeholder="https://cnp.example.com"
          />
          <div className="flex justify-end">
            <Button variant="primary" size="sm">Save</Button>
          </div>
        </div>
      </Card>

      {/* GitLab connection */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-foreground">GitLab connection</h2>
          {gitlabConnected === true && <Badge variant="success">Connected</Badge>}
          {gitlabConnected === false && <Badge variant="danger">Disconnected</Badge>}
          {gitlabConnected === null && <Badge variant="muted">Not verified</Badge>}
        </div>
        <div className="flex flex-col gap-3">
          <Input
            label="GitLab instance URL"
            value={gitlabUrl}
            onChange={(e) => setGitlabUrl(e.target.value)}
            placeholder="https://gitlab.example.com"
          />
          <Input
            label="Root group"
            value={gitlabGroup}
            onChange={(e) => setGitlabGroup(e.target.value)}
            placeholder="cnp-apps"
          />
          <Input
            label="Token service account"
            value={tokenVisible ? gitlabToken : gitlabToken ? '••••••••••••••••' : ''}
            onChange={(e) => setGitlabToken(e.target.value)}
            type={tokenVisible ? 'text' : 'password'}
            mono
            suffix={
              <button
                type="button"
                onClick={() => setTokenVisible((v) => !v)}
                className="text-muted-foreground"
              >
                {tokenVisible ? <IconEyeOff size={13} /> : <IconEye size={13} />}
              </button>
            }
          />
          <div className="flex gap-2 justify-end">
            <Button
              variant="secondary"
              size="sm"
              icon={<IconRefresh size={13} />}
              loading={healthMutation.isPending}
              onClick={() => healthMutation.mutate()}
            >
              Test connection
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={saveGitlabMutation.isPending}
              disabled={!gitlabToken || !gitlabGroup}
              onClick={() => saveGitlabMutation.mutate()}
            >
              Save
            </Button>
          </div>
        </div>
      </Card>

      {/* Register cluster */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Register cluster</h2>
        <div className="flex flex-col gap-3">
          <Input
            label="Name"
            value={clusterName}
            onChange={(e) => setClusterName(e.target.value)}
            placeholder="cnp-prod"
          />
          <Input
            label="Endpoint API"
            value={clusterEndpoint}
            onChange={(e) => setClusterEndpoint(e.target.value)}
            placeholder="https://k8s.example.com:6443"
            mono
          />
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">
              Kubeconfig
            </label>
            <textarea
              value={kubeconfigVisible ? kubeconfig : kubeconfig ? '••••••\n••••••\n••••••' : ''}
              onChange={(e) => setKubeconfig(e.target.value)}
              onFocus={() => setKubeconfigVisible(true)}
              onBlur={() => setKubeconfigVisible(false)}
              rows={5}
              placeholder="Paste kubeconfig content…"
              className="w-full px-3 py-2 text-xs font-mono rounded-md border border-input bg-background resize-none focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Kubeconfig is stored encrypted. Only the active context is used.
            </p>
          </div>
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              loading={registerClusterMutation.isPending}
              disabled={!clusterName || !clusterEndpoint || !kubeconfig}
              onClick={() => registerClusterMutation.mutate()}
            >
              Register cluster
            </Button>
          </div>
        </div>
      </Card>
      </div>
    </div>
  );
}
