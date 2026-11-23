"""Fichiers cnp-gitops d'un env éphémère (4K-286, ADR-0030 §4 à §7)."""

import yaml

from backend.gitops.ephemeral import EphemeralTarget, declaration_files

GITOPS_URL = "https://gitlab.com/4k-cnp-2027/cnp-gitops.git"


def _target(**kw) -> EphemeralTarget:
    base = dict(
        cluster="cnp-aks", app_slug="my-app", env_slug="feat-login", branch="feat/login",
        owner="team-a", gitops_repo_url=GITOPS_URL,
        registry_vault_key="secret/apps/_platform/gitlab-registry", registry_server="registry.gitlab.com",
    )
    base.update(kw)
    return EphemeralTarget(**base)


def _files() -> dict[str, dict]:
    return {f["file_path"]: yaml.safe_load(f["content"]) for f in declaration_files(_target())}


ROOT = "apps/cnp-aks/my-app/ephemeral/feat-login"


def test_chemins_des_fichiers():
    assert set(_files()) == {
        f"{ROOT}/env.yaml",
        f"{ROOT}/platform/namespace.yaml",
        f"{ROOT}/platform/registry-pull-secret.yaml",
        f"{ROOT}/platform/serviceaccount.yaml",
        f"{ROOT}/platform/app-env.yaml",
        f"{ROOT}/platform/certificate.yaml",
        "argocd/cnp-aks/my-app/ephemeral/feat-login--platform.yaml",
        "argocd/cnp-aks/my-app/ephemeral/feat-login--project.yaml",
    }


def test_declaration_lue_par_la_ci():
    decl = _files()[f"{ROOT}/env.yaml"]
    assert decl == {
        "app": "my-app",
        "slug": "feat-login",
        "name": "my-app--feat-login",
        "branch": "feat/login",
        "namespace": "my-app--feat-login",
    }


def test_namespace_gere_et_etiquete():
    ns = _files()[f"{ROOT}/platform/namespace.yaml"]
    assert ns["kind"] == "Namespace"
    assert ns["metadata"]["name"] == "my-app--feat-login"
    labels = ns["metadata"]["labels"]
    assert labels["cnp.io/app"] == "my-app"
    assert labels["cnp.io/env-type"] == "ephemeral"
    assert labels["cnp.io/owner"] == "team-a"


def test_namespace_pod_security_baseline():
    # Chart non relu : Pod Security Admission refuse les pods privilégiés et les accès à l'hôte
    labels = _files()[f"{ROOT}/platform/namespace.yaml"]["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "baseline"


def test_pull_secret_dockerconfigjson_depuis_vault():
    es = _files()[f"{ROOT}/platform/registry-pull-secret.yaml"]
    assert es["kind"] == "ExternalSecret"
    assert es["metadata"]["namespace"] == "my-app--feat-login"
    assert es["spec"]["secretStoreRef"] == {"name": "vault-backend", "kind": "ClusterSecretStore"}
    target = es["spec"]["target"]
    assert target["name"] == "gitlab-registry"
    assert target["template"]["type"] == "kubernetes.io/dockerconfigjson"
    assert "registry.gitlab.com" in target["template"]["data"][".dockerconfigjson"]
    keys = {d["remoteRef"]["key"] for d in es["spec"]["data"]}
    assert keys == {"secret/apps/_platform/gitlab-registry"}


def test_aucun_chemin_prod_dans_les_manifestes():
    for f in declaration_files(_target()):
        assert "/prod" not in f["content"]


def test_service_account_default_utilise_le_pull_secret():
    sa = _files()[f"{ROOT}/platform/serviceaccount.yaml"]
    assert sa["kind"] == "ServiceAccount"
    assert sa["metadata"] == {"name": "default", "namespace": "my-app--feat-login"}
    assert sa["imagePullSecrets"] == [{"name": "gitlab-registry"}]


def test_application_plateforme():
    app = _files()["argocd/cnp-aks/my-app/ephemeral/feat-login--platform.yaml"]
    assert app["kind"] == "Application"
    assert app["metadata"]["name"] == "my-app--feat-login--platform"
    assert app["metadata"]["namespace"] == "argocd"
    assert "resources-finalizer.argocd.argoproj.io" in app["metadata"]["finalizers"]
    spec = app["spec"]
    assert spec["project"] == "cnp-platform"
    assert spec["source"] == {"repoURL": GITOPS_URL, "targetRevision": "HEAD", "path": f"{ROOT}/platform"}
    assert spec["destination"] == {"server": "https://kubernetes.default.svc", "namespace": "my-app--feat-login"}
    assert spec["syncPolicy"]["automated"] == {"prune": True, "selfHeal": True}
    # Namespace géré : pas de CreateNamespace, sinon ArgoCD ne le supprime jamais
    assert "CreateNamespace=true" not in spec["syncPolicy"].get("syncOptions", [])


def test_url_gitops_sans_identifiants():
    files = declaration_files(_target(gitops_repo_url="https://oauth2:secret@gitlab.com/4k-cnp-2027/cnp-gitops.git"))
    app = next(yaml.safe_load(f["content"]) for f in files if f["file_path"].startswith("argocd/"))
    assert app["spec"]["source"]["repoURL"] == GITOPS_URL


def test_application_plateforme_reessaie_la_synchro():
    app = _files()["argocd/cnp-aks/my-app/ephemeral/feat-login--platform.yaml"]
    # Un ancien namespace du même nom peut encore être en Terminating
    assert app["spec"]["syncPolicy"]["retry"]["limit"] >= 5


def test_branches_x_et_x_platform_sans_collision():
    """Revue #82 : `login` et `login-platform` ne partagent ni fichier ni Application."""
    files_x = declaration_files(_target(env_slug="login", branch="login"))
    files_xp = declaration_files(_target(env_slug="login-platform", branch="login-platform"))
    paths_x = {f["file_path"] for f in files_x}
    paths_xp = {f["file_path"] for f in files_xp}
    assert paths_x.isdisjoint(paths_xp)
    # ... ni avec l'Application de l'app que update-gitops-ephemeral écrit dans <slug>.yaml
    app_files = {"argocd/cnp-aks/my-app/ephemeral/login.yaml", "argocd/cnp-aks/my-app/ephemeral/login-platform.yaml"}
    assert app_files.isdisjoint(paths_x | paths_xp)

    def app_name(files):
        return next(yaml.safe_load(f["content"]) for f in files if f["file_path"].startswith("argocd/"))["metadata"]["name"]

    names = {app_name(files_x), app_name(files_xp), "my-app--login", "my-app--login-platform"}
    assert len(names) == 4


def test_nom_de_l_application_plateforme_dans_la_limite_argocd():
    # Nom d'env au plus 53 caractères (release Helm) + "--platform" : 63, limite des labels
    t = _target(app_slug="a" * 30, env_slug="b" * 21)
    assert len(t.name) == 53
    app = next(yaml.safe_load(f["content"]) for f in declaration_files(t) if f["file_path"].startswith("argocd/"))
    assert len(app["metadata"]["name"]) <= 63


def test_chemins_de_destruction_couvrent_ce_que_cree_la_creation():
    from backend.gitops.ephemeral import deployment_files, destroy_paths, project_path

    files, directories = destroy_paths("cnp-aks", "my-app", "feat-login")
    project = project_path("cnp-aks", "my-app", "feat-login")
    created = {f["file_path"] for f in declaration_files(_target())}
    created |= {f["file_path"] for f in deployment_files(_target(), {}, "https://gitlab.com/g/my-app", "a" * 40)}
    # Tout fichier écrit par le backend est supprimé : directement, avec son dossier, ou
    # (l'AppProject) une fois les Applications disparues
    for path in created:
        assert path in files or path == project or any(path.startswith(d + "/") for d in directories)
    assert project not in files


def test_fichiers_de_deploiement():
    from backend.gitops.ephemeral import deployment_files

    sha = "0123456789abcdef0123456789abcdef01234567"
    source = {"image": {"repository": "registry.gitlab.com/g/my-app", "tag": "latest"},
              "ingress": {"enabled": True, "host": "dev.my-app.example"}, "replicaCount": 2}
    files = {f["file_path"]: yaml.safe_load(f["content"])
             for f in deployment_files(_target(), source, "https://oauth2:tok@gitlab.com/g/my-app", sha)}

    values = files[f"{ROOT}/values.yaml"]
    assert values["image"]["tag"] == "01234567"
    # Jamais le host de dev : celui de l'env, en TLS
    assert values["ingress"] == {
        "enabled": True, "host": "my-app--feat-login.cloud-native-plat4k.me", "className": "nginx", "tls": True,
    }
    assert values["replicaCount"] == 2
    assert values["app"]["owner"] == "team-a"
    assert source["image"]["tag"] == "latest"  # la source n'est pas modifiée

    app = files["argocd/cnp-aks/my-app/ephemeral/feat-login.yaml"]
    assert app["metadata"]["name"] == "my-app--feat-login"
    assert "resources-finalizer.argocd.argoproj.io" in app["metadata"]["finalizers"]
    spec = app["spec"]
    assert spec["project"] == "my-app--feat-login"  # AppProject propre à l'env
    chart, gitops = spec["sources"]
    assert chart == {
        "repoURL": "https://gitlab.com/g/my-app.git",  # sans identifiants
        "targetRevision": sha,
        "path": "chart",
        "helm": {"valueFiles": [f"$gitops/{ROOT}/values.yaml"]},
    }
    assert gitops == {"repoURL": GITOPS_URL, "targetRevision": "HEAD", "ref": "gitops"}
    assert spec["destination"]["namespace"] == "my-app--feat-login"
    assert spec["syncPolicy"]["retry"]["limit"] >= 5


def _tfiles(**kw) -> dict[str, dict]:
    return {f["file_path"]: yaml.safe_load(f["content"]) for f in declaration_files(_target(**kw))}


def test_variables_heritees_de_dev_sans_copie():
    es = _tfiles(vault_env_path="secret/apps/team-a/my-app/dev")[f"{ROOT}/platform/app-env.yaml"]
    assert es["kind"] == "ExternalSecret"
    assert es["metadata"] == {"name": "my-app-env", "namespace": "my-app--feat-login"}
    # Même Secret que dev (<app>-env, monté en envFrom par le chart), lu dans le chemin dev
    assert es["spec"]["target"]["name"] == "my-app-env"
    assert es["spec"]["target"]["deletionPolicy"] == "Delete"
    assert es["spec"]["dataFrom"] == [{"extract": {"key": "secret/apps/team-a/my-app/dev"}}]


def test_certificat_du_host_de_l_env():
    cert = _tfiles(tls_issuer="letsencrypt-staging")[f"{ROOT}/platform/certificate.yaml"]
    assert cert["kind"] == "Certificate"
    assert cert["metadata"] == {"name": "my-app-tls", "namespace": "my-app--feat-login"}
    assert cert["spec"]["secretName"] == "my-app-tls"  # celui de l'Ingress du chart
    assert cert["spec"]["dnsNames"] == ["my-app--feat-login.cloud-native-plat4k.me"]
    assert cert["spec"]["issuerRef"] == {"name": "letsencrypt-staging", "kind": "ClusterIssuer", "group": "cert-manager.io"}


def test_appproject_limite_au_namespace_de_l_env():
    """Revue de cnp-gitops !4 : le chart de l'app A ne peut pas déployer dans un env de B."""
    proj = _tfiles(app_repo_url="https://gitlab.com/4k-cnp-2027/cnp-apps/my-app")[
        "argocd/cnp-aks/my-app/ephemeral/feat-login--project.yaml"]
    assert proj["kind"] == "AppProject"
    assert proj["metadata"]["name"] == "my-app--feat-login"
    assert proj["metadata"]["namespace"] == "argocd"
    spec = proj["spec"]
    assert spec["destinations"] == [{"server": "https://kubernetes.default.svc", "namespace": "my-app--feat-login"}]
    assert spec["sourceRepos"] == ["https://gitlab.com/4k-cnp-2027/cnp-apps/my-app.git", GITOPS_URL]
    assert spec["clusterResourceWhitelist"] == []
    blacklisted = {(r["group"], r["kind"]) for r in spec["namespaceResourceBlacklist"]}
    for kind in [("external-secrets.io", "ExternalSecret"), ("cert-manager.io", "Certificate"),
                 ("cert-manager.io", "Issuer"), ("", "ResourceQuota")]:
        assert kind in blacklisted


def test_host_a_un_seul_label_sous_le_domaine():
    t = _target()
    assert t.host == "my-app--feat-login.cloud-native-plat4k.me"
    assert t.host.count(".") == 2  # couvert par un futur wildcard *.cloud-native-plat4k.me
