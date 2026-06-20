import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useScopeStore } from '@/store/scope';
import { appsApi } from '@/api/apps';
import { useToast } from '@/components/ui/toast';
import { Step1Data, ServiceConfig, CiDeployConfig } from '@/types';
import { computeSlug } from '@/utils/slugify';
import { StepperBar } from './StepperBar';
import { Step1Identity } from './Step1Identity';
import { Step2Services } from './Step2Services';
import { Step3CiDeploy } from './Step3CiDeploy';
import { Step4Recap } from './Step4Recap';

const STEP_LABELS = ['Identité', 'Services', 'CI & Déploiement', 'Récap'];

export function NewApp() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const group = useCurrentGroup();
  const { setScope } = useScopeStore();
  const qc = useQueryClient();

  useEffect(() => {
    if (slug) setScope('group', slug);
  }, [slug, setScope]);

  const [step, setStep] = useState(1);
  const [step1, setStep1] = useState<Step1Data>({
    origin: 'scaffold',
    name: '',
    framework: '',
    repoUrl: '',
  });
  const [step2, setStep2] = useState<ServiceConfig>({
    database: { enabled: false, dbName: '', pgSize: '1Gi' },
    auth: { enabled: false },
    cache: { enabled: false },
  });
  const [step3, setStep3] = useState<CiDeployConfig>({
    trigger: 'on_commit',
    envVars: [],
    replicas: 1,
    targetClusterId: null,
    advancedOpen: false,
  });
  const { toast } = useToast();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (step1.origin === 'scaffold') {
        return appsApi.scaffoldApp({
          name: step1.name,
          template_id: step1.framework,
          owning_gitlab_group_id: group?.gitlab_group_id,
        });
      } else {
        return appsApi.onboardApp({
          name: step1.name,
          repo_url: step1.repoUrl,
          owning_gitlab_group_id: group?.gitlab_group_id,
        });
      }
    },
    onSuccess: (app) => {
      qc.invalidateQueries({ queryKey: ['apps'] });
      toast({ title: 'Application créée', description: `${app.name} est en cours de provisioning.` });
      const appSlug = computeSlug(app.name);
      navigate(`/groups/${slug}/apps/${appSlug}`);
    },
    onError: () => {
      setSubmitError('Erreur lors de la création. Réessayez.');
      toast({ title: 'Erreur', variant: 'destructive' });
    },
  });

  const steps = STEP_LABELS.map((label, i) => ({
    label,
    state:
      i + 1 < step ? ('done' as const) : i + 1 === step ? ('active' as const) : ('todo' as const),
  }));

  return (
    <div className="max-w-xl mx-auto px-6 py-8">
      <StepperBar steps={steps} />

      {step === 1 && (
        <Step1Identity
          data={step1}
          onChange={(d) => setStep1((p) => ({ ...p, ...d }))}
          onNext={() => setStep(2)}
          onCancel={() => navigate(`/groups/${slug}/apps`)}
        />
      )}
      {step === 2 && (
        <Step2Services
          data={step2}
          onChange={(d) => setStep2((p) => ({ ...p, ...d }))}
          onNext={() => setStep(3)}
          onBack={() => setStep(1)}
        />
      )}
      {step === 3 && (
        <Step3CiDeploy
          data={step3}
          onChange={(d) => setStep3((p) => ({ ...p, ...d }))}
          onNext={() => setStep(4)}
          onBack={() => setStep(2)}
        />
      )}
      {step === 4 && (
        <Step4Recap
          identity={step1}
          services={step2}
          ciDeploy={step3}
          onSubmit={() => createMutation.mutate()}
          onBack={() => setStep(3)}
          isPending={createMutation.isPending}
          error={submitError}
        />
      )}
    </div>
  );
}
