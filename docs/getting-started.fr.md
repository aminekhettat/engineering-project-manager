# Votre premier projet

## Préparer et installer

Le runtime nécessite Linux, Python 3.10+ et Git, sans dépendance Python tierce.
Utilisez Linux/WSL sur Windows. Pour créer un dépôt, prévoyez une session `gh`
(GitHub) ou `glab` (GitLab) authentifiée. Un remote SSH nécessite aussi une identité
SSH configurée. N'inscrivez jamais de secret dans le questionnaire.

Depuis votre workspace OpenClaw, avec Node.js 22.20+ / npm :

```sh
npx skills@1.6.0 add aminekhettat/openclaw-project-manager --skill project-manager -a openclaw --copy
```

Vérifiez la destination proposée. La variable `DISABLE_TELEMETRY=1` désactive la
télémétrie de l'installateur. Évitez une installation globale si vous souhaitez
limiter le skill à ce workspace.

Autre possibilité : téléchargez le ZIP `project-manager-VERSION.zip` et son fichier
`.sha256` depuis les [releases](https://github.com/aminekhettat/openclaw-project-manager/releases/latest).
Exécutez `sha256sum -c project-manager-VERSION.zip.sha256`, puis extrayez le dossier
complet `project-manager/` dans `<OPENCLAW_WORKSPACE>/skills/` ou votre répertoire
de skills gérés. Depuis un clone source, copiez `skills/project-manager/` ; la
racine du dépôt contient les ressources destinées aux contributeurs.

Démarrez une nouvelle session agent. `openclaw skills info project-manager`
permet de vérifier la découverte et les prérequis.

## Cadrer le projet

> Utilise project-manager. Cherche d'abord le projet existant. Pose les questions
> manquantes par petits groupes et présente la configuration avant de créer
> l'infrastructure.

Le cadrage couvre objectif et périmètre, critères d'acceptation, disciplines,
responsables, contraintes, dépôt et branche, CI, environnement d'exécution,
références aux moyens d'authentification, délégation, jalons et obligations externes.
Les réponses déjà connues sont réutilisées. Une initialisation neuve crée un dépôt
remote ; elle ne reprend pas silencieusement un remote déjà rempli.

Pour un projet existant, demandez un état et une proposition de migration en
lecture seule. La migration doit être décidée explicitement.

## Lire les résultats

Depuis le dossier du skill installé, remplacez `PROJECT` par le chemin absolu du projet :

```sh
python3 scripts/migration_assess.py PROJECT --json
python3 scripts/project_report.py PROJECT --json
python3 scripts/project_state.py ready PROJECT
python3 scripts/release_check.py PROJECT
```

Les deux premières commandes sont en lecture seule. Un projet fraîchement créé
n'est pas prêt à livrer : ses travaux et preuves restent à produire. Un contrôle
en échec doit conduire à examiner les blocages, pas à inventer des preuves.

## Mettre à jour

Sauvegardez les adaptations locales, remplacez le runtime par une version revue,
puis redémarrez la session agent et contrôlez la découverte. Cela ne migre pas les
registres existants ni les copies d'outils générées dans les projets. Évaluez ces
mises à niveau séparément. Consultez la [compatibilité](compatibility.md) et
utilisez des données fictives pour tout [signalement](../CONTRIBUTING.md).
