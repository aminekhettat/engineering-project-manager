# Project Manager pour OpenClaw

**Passer d'une intention à des travaux revus, des preuves traçables et une livraison contrôlée.**

[![Contrôles](https://github.com/aminekhettat/engineering-project-manager/actions/workflows/checks.yml/badge.svg)](https://github.com/aminekhettat/engineering-project-manager/actions/workflows/checks.yml)
[![Version](https://img.shields.io/github/v/release/aminekhettat/engineering-project-manager)](https://github.com/aminekhettat/engineering-project-manager/releases/latest)
[![Licence MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README.md) · [Démarrage](docs/getting-started.fr.md) · [Démonstration](examples/release-gate/README.md) · [Compatibilité](docs/compatibility.md)

Ce skill aide un agent à cadrer un projet d'ingénierie, poser les questions de
configuration, déléguer des tâches bornées et maintenir la cohérence entre
exigences, changements, baselines, preuves, risques et jalons. Des commandes
Python déterministes contrôlent les données qui appuient la décision de livraison.

![Découvrir, configurer, déléguer, vérifier et contrôler la livraison. La démonstration passe de 1 test réussi sur 3 et une livraison bloquée à 3 tests réussis et un contrôle complet passant.](docs/assets/workflow.svg)

**SPICE-like, non certifié.** Outil indépendant, sans certification SPICE ou
Automotive SPICE, ni approbation d'un organisme de normalisation. Un contrôle
réussi ne constitue pas une évaluation de conformité ou un niveau de capacité.
[Périmètre et limites](skills/project-manager/docs/SPICE-SCOPE.md).

## Installer

Prérequis : **Linux, Python 3.10+ et Git**. Aucune dépendance Python à installer.
Depuis votre workspace OpenClaw, avec Node.js 22.20+ / npm pour cet installateur :

```sh
npx skills@1.6.0 add aminekhettat/engineering-project-manager --skill project-manager -a openclaw --copy
```

Vérifiez la destination proposée. Vous pouvez aussi télécharger le ZIP du runtime
et son SHA-256 depuis les [versions publiées](https://github.com/aminekhettat/engineering-project-manager/releases/latest),
vérifier l'empreinte et extraire `project-manager/` dans votre répertoire de skills.
Démarrez une nouvelle session agent. [Guide détaillé](docs/getting-started.fr.md).

## Trois points d'entrée

**Initialiser**

> Utilise project-manager. Cherche d'abord si le projet existe, puis pose les
> questions manquantes sur le périmètre, les disciplines, le dépôt, l'infrastructure,
> l'équipe, la délégation et la livraison. Présente la configuration avant création.

**Reprendre un projet**

> Analyse ce dépôt avec project-manager sans modifier ses registres. Présente
> l'état, les preuves manquantes, les blocages et la prochaine action prioritaire.

**Préparer une livraison**

> Vérifie ce candidat avec project-manager : révisions d'exigences, preuves,
> risques, problèmes et jalons. Explique les blocages. N'invente aucune acceptation
> ni preuve pour faire passer les contrôles.

## Essayer la démonstration

Depuis un clone complet du dépôt sous Linux :

```sh
python3 tools/demo_project.py --output /tmp/pm-demo
```

La destination doit être nouvelle. Hors réseau, le script reproduit un défaut
sur un petit programme : **1 test sur 3 passe**, puis **3 sur 3** après correction.
Le contrôle complet passe de **BLOCKED à PASS**, avec tâche revue, risque atténué,
problème fermé, jalon atteint, preuve liée à la révision exacte et baseline gelée.
[Procédure et sortie réellement capturée](examples/release-gate/README.md).
Il s'agit d'un exemple fictif, pas d'un benchmark de modèles ni d'un audit industriel.

## Capacités

| Besoin | Réponse du skill |
| --- | --- |
| Bien démarrer | Questionnaire, configuration revue, initialisation GitHub/GitLab et reprise après interruption. |
| Déléguer avec contrôle | Découverte des capacités, contrat borné, travail isolé et retour revu ; l'exécution dépend du runtime agent. |
| Maîtriser les changements | Identifiants d'exigences stables, révisions exactes, analyse d'impact et snapshots gelés immuables. |
| Justifier la livraison | Preuves de vérification, empreintes d'artefacts et contrôle composé de préparation à la livraison. |
| Suivre les blocages | Risques, problèmes, jalons, sources externes et couverture des obligations. |
| Adapter les disciplines | Systèmes, logiciel, matériel, ML, mécanique et cybersécurité. |

La revue d'ingénierie, les autorisations, l'acceptation des risques et la réalité
des essais restent des responsabilités humaines. [Capacités et limites](skills/project-manager/docs/INDUSTRIALIZATION-ROADMAP.md).

## Aller plus loin

[Architecture](docs/architecture.md) · [Compatibilité](docs/compatibility.md) ·
[Positionnement](docs/comparison.md) · [Contribuer](CONTRIBUTING.md) ·
[Versions](CHANGELOG.md) · [Sécurité](SECURITY.md) · [Publication](docs/PUBLICATION.md)

Signalez un [bug reproductible](https://github.com/aminekhettat/engineering-project-manager/issues/new/choose)
ou partagez un cas d'usage dans les [discussions](https://github.com/aminekhettat/engineering-project-manager/discussions).
Les sources et archives GitHub sont sous [MIT](LICENSE). La distribution ClawHub,
générée séparément, utilise MIT-0 conformément aux règles du registre. Les standards
externes conservent leurs propres droits. Les exemples partagés doivent être anonymisés.
