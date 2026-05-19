import { useState } from 'react';

/* ── Types ── */
type DocPageId =
  | 'premiers-pas'
  | 'scaffolder'
  | 'importer'
  | 'deployer'
  | 'api-rest'
  | 'cli'
  | 'faq';

interface NavSection {
  section: string;
  icon: string;
  items: [DocPageId, string][];
}

/* ── Nav structure ── */
const NAV: NavSection[] = [
  {
    section: 'Guides',
    icon: 'ti-rocket',
    items: [
      ['premiers-pas', 'Premiers pas'],
      ['scaffolder', 'Scaffolder une app'],
      ['importer', 'Importer un repo'],
      ['deployer', 'Déployer sur AKS'],
    ],
  },
  {
    section: 'Référence',
    icon: 'ti-code',
    items: [
      ['api-rest', 'API REST'],
      ['cli', 'CLI cnp'],
    ],
  },
  {
    section: 'FAQ',
    icon: 'ti-help-circle',
    items: [['faq', 'Questions fréquentes']],
  },
];

/* ── Sub-components ── */
const CodeBlock = ({ children }: { children: string }) => (
  <div className="doc-code-block">{children}</div>
);

const Callout = ({ type, children }: { type: 'info' | 'tip'; children: string }) => (
  <div className={`doc-callout ${type}`}>
    <i className={`ti ${type === 'info' ? 'ti-info-circle' : 'ti-bulb'}`} aria-hidden="true" />
    <span>{children}</span>
  </div>
);

function NavBtn({
  to,
  label,
  dir,
  onClick,
}: {
  to: DocPageId;
  label: string;
  dir: 'prev' | 'next';
  onClick: (p: DocPageId) => void;
}) {
  return (
    <button className={`doc-nav-btn${dir === 'next' ? ' next' : ''}`} onClick={() => onClick(to)}>
      <span className="doc-nav-label">{dir === 'next' ? 'Suivant' : 'Précédent'}</span>
      <span className="doc-nav-title">
        {dir !== 'next' && <i className="ti ti-arrow-left" aria-hidden="true" />}
        {label}
        {dir === 'next' && <i className="ti ti-arrow-right" aria-hidden="true" />}
      </span>
    </button>
  );
}

/* ── Pages content ── */
function PageContent({
  page,
  openFaq,
  setOpenFaq,
  nav,
}: {
  page: DocPageId;
  openFaq: number | null;
  setOpenFaq: (i: number | null) => void;
  nav: (p: DocPageId) => void;
}) {
  if (page === 'premiers-pas') return (
    <>
      <div className="doc-breadcrumb">
        <span>Guides</span><i className="ti ti-chevron-right" aria-hidden="true" /><span>Premiers pas</span>
      </div>
      <h1 className="doc-h1">Premiers pas avec CNP</h1>
      <p className="doc-lead">
        CNP est une Internal Developer Platform qui vous permet de scaffolder, déployer et observer des applications conteneurisées sur Kubernetes, sans connaissance préalable de k8s ou Terraform.
      </p>
      <h2 className="doc-h2">Installer le CLI</h2>
      <CodeBlock>{`# Installer via pip\npip install cnp-cli\n\n# Configurer votre token\ncnp auth login --token cnp_xxxxxxxxxxxx\n\n# Vérifier la connexion\ncnp status`}</CodeBlock>
      <Callout type="info">Le CLI stocke votre configuration dans ~/.cnp/config.toml. Ne commitez jamais ce fichier dans un repo Git.</Callout>
      <h2 className="doc-h2">Votre première application</h2>
      <div className="doc-steps">
        {[
          ['Choisir un template', 'Depuis la page Templates, sélectionnez FastAPI — Python et cliquez sur Utiliser.'],
          ['Nommer votre application', 'CNP crée automatiquement un repo GitLab et pousse le code scaffoldé.'],
          ['Déployer', 'CNP build l\'image Docker, la pousse dans le registry et déploie sur AKS.'],
        ].map(([title, desc], i) => (
          <div key={i} className="doc-step">
            <div className="step-num">{i + 1}</div>
            <div>
              <div className="step-title">{title}</div>
              <div className="step-desc">{desc}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="doc-nav-footer">
        <div />
        <NavBtn to="scaffolder" label="Scaffolder une app" dir="next" onClick={nav} />
      </div>
    </>
  );

  if (page === 'scaffolder') return (
    <>
      <div className="doc-breadcrumb">
        <span>Guides</span><i className="ti ti-chevron-right" aria-hidden="true" /><span>Scaffolder une app</span>
      </div>
      <h1 className="doc-h1">Scaffolder une application</h1>
      <p className="doc-lead">
        Le scaffolding génère un projet prêt-à-déployer depuis un template officiel CNP, avec Dockerfile, manifests Kubernetes et pipeline CI/CD préconfigurés.
      </p>
      <h2 className="doc-h2">Via le CLI</h2>
      <CodeBlock>{`# Lister les templates disponibles\ncnp template list\n\n# Scaffolder une app FastAPI\ncnp app create --template fastapi --name mon-service\n\n# Cloner le repo généré\ngit clone gitlab.cri.epita.fr/votre-namespace/mon-service`}</CodeBlock>
      <Callout type="tip">CNP crée un repo GitLab dans votre namespace et pousse le code généré. Vous pouvez cloner et commencer à coder immédiatement.</Callout>
      <div className="doc-nav-footer">
        <NavBtn to="premiers-pas" label="Premiers pas" dir="prev" onClick={nav} />
        <NavBtn to="importer" label="Importer un repo" dir="next" onClick={nav} />
      </div>
    </>
  );

  if (page === 'importer') return (
    <>
      <div className="doc-breadcrumb">
        <span>Guides</span><i className="ti ti-chevron-right" aria-hidden="true" /><span>Importer un repo</span>
      </div>
      <h1 className="doc-h1">Importer un repo existant</h1>
      <p className="doc-lead">
        CNP peut gérer le déploiement d'un repo GitLab existant sans scaffolding. Votre repo doit contenir un Dockerfile et des manifests Kubernetes valides.
      </p>
      <h2 className="doc-h2">Structure attendue</h2>
      <CodeBlock>{`mon-service/\n  Dockerfile\n  k8s/\n    deployment.yaml\n    service.yaml\n  .gitlab-ci.yml   # optionnel si CI CNP activée`}</CodeBlock>
      <div className="doc-nav-footer">
        <NavBtn to="scaffolder" label="Scaffolder une app" dir="prev" onClick={nav} />
        <NavBtn to="deployer" label="Déployer sur AKS" dir="next" onClick={nav} />
      </div>
    </>
  );

  if (page === 'deployer') return (
    <>
      <div className="doc-breadcrumb">
        <span>Guides</span><i className="ti ti-chevron-right" aria-hidden="true" /><span>Déployer sur AKS</span>
      </div>
      <h1 className="doc-h1">Déployer sur AKS</h1>
      <p className="doc-lead">
        CNP orchestre le déploiement de vos applications sur Azure Kubernetes Service via un pipeline GitLab CI.
      </p>
      <CodeBlock>{`cnp app deploy --app mon-service --env production`}</CodeBlock>
      <Callout type="info">Le cluster AKS est en autoscale 2–4 nodes. Utilisez az aks stop pour réduire les coûts hors usage.</Callout>
      <div className="doc-nav-footer">
        <NavBtn to="importer" label="Importer un repo" dir="prev" onClick={nav} />
        <NavBtn to="api-rest" label="API REST" dir="next" onClick={nav} />
      </div>
    </>
  );

  if (page === 'api-rest') return (
    <>
      <div className="doc-breadcrumb">
        <span>Référence</span><i className="ti ti-chevron-right" aria-hidden="true" /><span>API REST</span>
      </div>
      <h1 className="doc-h1">API REST</h1>
      <p className="doc-lead">
        L'API CNP expose les ressources de la plateforme via HTTP/JSON. Authentification via Bearer token ou header X-API-Key.
      </p>
      <h2 className="doc-h2">Base URL</h2>
      <CodeBlock>https://api.cnp.epita.fr/v1</CodeBlock>
      <h2 className="doc-h2">Endpoints principaux</h2>
      <table className="doc-table">
        <thead>
          <tr><th>Endpoint</th><th>Méthode</th><th>Description</th></tr>
        </thead>
        <tbody>
          {[
            ['GET /applications', 'GET', 'Lister les applications'],
            ['POST /applications', 'POST', 'Créer une application'],
            ['GET /applications/:id', 'GET', 'Détail d\'une application'],
            ['POST /deployments', 'POST', 'Déclencher un déploiement'],
            ['GET /templates', 'GET', 'Lister les templates'],
          ].map(([ep, m, d]) => (
            <tr key={ep}><td>{ep}</td><td>{m}</td><td>{d}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="doc-nav-footer">
        <NavBtn to="deployer" label="Déployer sur AKS" dir="prev" onClick={nav} />
        <NavBtn to="cli" label="CLI cnp" dir="next" onClick={nav} />
      </div>
    </>
  );

  if (page === 'cli') return (
    <>
      <div className="doc-breadcrumb">
        <span>Référence</span><i className="ti ti-chevron-right" aria-hidden="true" /><span>CLI cnp</span>
      </div>
      <h1 className="doc-h1">CLI cnp</h1>
      <p className="doc-lead">
        Le CLI CNP est un client Python (Typer) qui expose toutes les fonctionnalités de la plateforme en ligne de commande.
      </p>
      <table className="doc-table">
        <thead>
          <tr><th>Commande</th><th>Description</th></tr>
        </thead>
        <tbody>
          {[
            ['cnp auth login', 'Configurer le token d\'accès'],
            ['cnp app list', 'Lister vos applications'],
            ['cnp app create', 'Scaffolder une nouvelle app'],
            ['cnp app deploy', 'Déclencher un déploiement'],
            ['cnp app logs', 'Afficher les logs en live'],
            ['cnp template list', 'Lister les templates'],
            ['cnp status', 'Vérifier la connexion à l\'API'],
          ].map(([cmd, desc]) => (
            <tr key={cmd}><td>{cmd}</td><td>{desc}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="doc-nav-footer">
        <NavBtn to="api-rest" label="API REST" dir="prev" onClick={nav} />
        <NavBtn to="faq" label="FAQ" dir="next" onClick={nav} />
      </div>
    </>
  );

  if (page === 'faq') return (
    <>
      <div className="doc-breadcrumb">
        <span>FAQ</span><i className="ti ti-chevron-right" aria-hidden="true" /><span>Questions fréquentes</span>
      </div>
      <h1 className="doc-h1">Questions fréquentes</h1>
      <p className="doc-lead">Les réponses aux questions les plus courantes sur l'utilisation de CNP.</p>
      {[
        ['Mon déploiement est bloqué en Déploiement… depuis plusieurs minutes.', 'Vérifiez les logs de votre application. Un pod en CrashLoopBackOff indique un crash applicatif. Un pod en Pending indique un manque de ressources sur le cluster.'],
        ['Comment réduire les coûts quand je n\'utilise pas le cluster ?', 'Utilisez az aks stop --name cnp-aks-sweden --resource-group cnp-rg pour arrêter le cluster. Le démarrage prend 3–5 minutes avec az aks start.'],
        ['Puis-je déployer sur plusieurs clusters en même temps ?', 'Le multi-cluster est prévu pour la Phase 2. En Phase 1, chaque application est associée à un seul cluster cible.'],
        ['Comment ajouter des variables d\'environnement secrètes ?', 'Les secrets sont gérés via Kubernetes Secrets. Depuis la page de votre application, Configuration > Variables d\'environnement, les valeurs sont chiffrées au repos.'],
        ['Mon image Docker ne se build pas dans la CI GitLab.', 'Vérifiez que votre Dockerfile est à la racine du repo et que le runner GitLab a accès au registry registry.cri.epita.fr.'],
      ].map(([q, a], i) => (
        <div key={i} className="faq-item" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
          <div className="faq-q">
            {q}
            <i className={`ti ti-chevron-${openFaq === i ? 'up' : 'down'}`} aria-hidden="true" />
          </div>
          {openFaq === i && <div className="faq-a">{a}</div>}
        </div>
      ))}
      <div className="doc-nav-footer">
        <NavBtn to="cli" label="CLI cnp" dir="prev" onClick={nav} />
        <div />
      </div>
    </>
  );

  return null;
}

/* ── Main component ── */
export const Docs = () => {
  const [page, setPage] = useState<DocPageId>('premiers-pas');
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Documentation</span>
        <div className="filter-select" style={{ minWidth: 200 }}>
          <i className="ti ti-search" style={{ fontSize: 13 }} aria-hidden="true" />
          Rechercher dans la doc…
        </div>
      </div>

      <div className="docs-layout">
        <nav className="docs-nav">
          {NAV.map(s => (
            <div key={s.section} className="docs-nav-section">
              <div className="docs-nav-section-label">
                <i className={`ti ${s.icon}`} aria-hidden="true" />
                {s.section}
              </div>
              {s.items.map(([id, label]) => (
                <button
                  key={id}
                  className={`docs-nav-item${page === id ? ' active' : ''}`}
                  onClick={() => { setPage(id); setOpenFaq(null); }}
                >
                  {label}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="docs-content">
          <PageContent
            page={page}
            openFaq={openFaq}
            setOpenFaq={setOpenFaq}
            nav={(p) => { setPage(p); setOpenFaq(null); }}
          />
        </div>
      </div>
    </>
  );
};
