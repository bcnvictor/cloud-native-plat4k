# ci-modules — fichiers à pousser dans `cnp-ci-modules`

Ces fichiers sont une **copie de staging** des nouveaux modules framework à ajouter au
repo GitLab `4k-cnp-2027/cnp-ci-modules` (référencé par `GITLAB_CI_PROJECT`). Ils ne
sont pas lus depuis ce dépôt — la CNP les inclut depuis GitLab via le `.gitlab-ci.yml`
qu'elle génère.

## Fichiers

| Fichier | Job | Déclenchement (`rules: exists`) |
|---------|-----|--------------------------------|
| `frameworks/nodejs.yml` | `nodejs-test` (`npm run test --if-present`) | `package.json` |
| `frameworks/go.yml`     | `go-test` (`go test ./...`)                 | `go.mod` |

## Mise en place

À pousser à la **racine** de `cnp-ci-modules`, à côté de `base/pipeline.yml` et
`frameworks/python.yml` existants :

```bash
# depuis un clone de cnp-ci-modules
cp <plat4k>/templates/ci-modules/frameworks/nodejs.yml frameworks/
cp <plat4k>/templates/ci-modules/frameworks/go.yml     frameworks/
git add frameworks/nodejs.yml frameworks/go.yml
git commit -m "feat(4K-57): add nodejs and go framework CI modules"
git push
```

> `base/pipeline.yml` n'a **pas** besoin d'être modifié : c'est le `.gitlab-ci.yml`
> généré par la plateforme qui sélectionne le bon `frameworks/<framework>.yml` à
> inclure, en fonction du framework détecté/du template (voir
> `backend/ci/templates.py` côté plateforme).
