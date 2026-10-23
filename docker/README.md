# Environnement de test : deux hôtes Debian + systemd

Outillage de test local **optionnel** pour `mla` : utile pour essayer l'outil
et vérifier l'idempotence, mais `mla` n'en dépend pas.
Deux conteneurs Debian 12 (bookworm) qui démarrent `systemd`, avec `sshd` et un
utilisateur non privilégié `mla` qui a `sudo` avec mot de passe, joignables en
SSH depuis la machine hôte.

## Contenu

| Hôte  | IP conteneur  | Port publié (localhost) | User  | Mot de passe | Clé attendue            |
|-------|---------------|-------------------------|-------|--------------|-------------------------|
| host1 | `172.28.0.11` | `127.0.0.1:2221`        | `mla` | `mla`        | `~/.ssh/id_ed25519_mla` |
| host2 | `172.28.0.12` | `127.0.0.1:2222`        | `mla` | `mla`        | `~/.ssh/id_ed25519_mla` |

Ces identifiants ne servent qu'à ces conteneurs jetables, joignables uniquement
depuis la machine locale.

- `mla` a `sudo` **avec** mot de passe (`/etc/sudoers.d/mla`, sans
  `NOPASSWD`). Le mot de passe du compte (`mla`) sert à la fois pour
  l'authentification SSH (`ssh_password`) et pour `sudo -S` dans les modules
  `apt`, `service` et `sysctl`.
- `PasswordAuthentication` est activé : les trois méthodes d'authentification
  de `mla` sont testables.
- Les clés d'hôte SSH sont figées dans l'image : elles ne changent qu'au
  **rebuild**, pas à chaque `up`/`down`.

## Prérequis

- Docker Engine et le plugin `compose` (v2.15 ou plus récent, pour la clé
  `cgroup:`).
- Une machine hôte en cgroup v2 (`stat -fc %T /sys/fs/cgroup` affiche
  `cgroup2fs`), ce qui est le cas par défaut des distributions récentes.

## 1. Générer la clé de test (une seule fois)

Le fichier `compose` monte `~/.ssh/id_ed25519_mla.pub` dans les conteneurs. Il
faut la créer **avant** le premier `up`, sinon Docker crée un dossier à la
place du fichier :

```sh
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_mla -N "" -C mla-test
```

Pour utiliser une autre clé : `export MLA_PUBKEY=/chemin/vers/cle.pub`.

## 2. Construire et démarrer

Depuis ce dossier (`docker/`) :

```sh
docker compose up -d --build
```

Vérifier que systemd tourne dans les deux conteneurs :

```sh
docker compose ps
docker compose exec host1 systemctl is-system-running   # "running" ou "degraded" = OK
docker compose exec host2 systemctl list-units --type=service --state=running
```

`degraded` est acceptable (un service masqué qui se plaint) tant que `ssh` et le
reste tournent.

## 3. Se connecter

```sh
# Clé privée (ssh_key_file), via l'IP du conteneur
ssh -i ~/.ssh/id_ed25519_mla mla@172.28.0.11

# Utilisateur et mot de passe (ssh_user + ssh_password), via le port publié
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -p 2222 mla@127.0.0.1        # mot de passe : mla

# Configuration par défaut : ajouter un bloc Host dans ~/.ssh/config
#   Host mla-host1
#       HostName 172.28.0.11
#       User mla
#       IdentityFile ~/.ssh/id_ed25519_mla
# puis : ssh mla-host1
# mla lit ce même fichier : un hôte d'inventaire avec seulement
# "ssh_address: mla-host1" se connecte comme "ssh mla-host1".

# Vérifier sudo avec mot de passe. mla envoie le mot de passe sur l'entrée
# standard du canal SSH (sudo -S), jamais dans la ligne de commande :
ssh -i ~/.ssh/id_ed25519_mla mla@172.28.0.11 \
    "sudo -S -p '' systemctl restart ssh && echo OK" <<< mla
```

Après un rebuild, si SSH signale un changement de clé d'hôte :
`ssh-keygen -R 172.28.0.11` (et `.12`, `[127.0.0.1]:2221`, `[127.0.0.1]:2222`).

## 4. Remplir l'inventaire

[`inventory.example.yml`](../inventory.example.yml) à la racine du dépôt est
prêt pour ces conteneurs : `cp inventory.example.yml inventory.yml`.

Les IP des conteneurs (`172.28.0.x`, port 22) et les ports publiés
(`127.0.0.1:222x`) fonctionnent tous les deux. Avec `127.0.0.1`, les logs
affichent `host=127.0.0.1:2221` et `host=127.0.0.1:2222` pour distinguer les
deux hôtes. Pour `apt`, `service` et `sysctl`, renseigner `ssh_password` (mot
de passe sudo) même sur un hôte qui se connecte par clé.

```yaml
hosts:
  host1:
    ssh_address: 172.28.0.11
    ssh_port: 22
    ssh_user: mla
    ssh_key_file: ~/.ssh/id_ed25519_mla
    ssh_password: mla
  host2:
    ssh_address: 172.28.0.12
    ssh_port: 22
    ssh_user: mla
    ssh_password: mla
```

## 5. Cycle de vie

| Action                         | Commande                                                  |
|--------------------------------|-----------------------------------------------------------|
| Démarrer                       | `docker compose up -d`                                    |
| Arrêter (garde les conteneurs) | `docker compose stop`                                     |
| Redémarrer                     | `docker compose restart`                                  |
| Détruire conteneurs et réseau  | `docker compose down`                                     |
| Détruire aussi l'image         | `docker compose down --rmi local`                         |
| Reconstruire à neuf            | `docker compose build --no-cache && docker compose up -d` |
| Shell root dans un hôte        | `docker compose exec host1 bash`                          |
| Logs de démarrage systemd      | `docker compose logs host1`                               |

## Remise à zéro d'un hôte

Pour retester l'idempotence depuis un état propre, le plus simple est de
recréer le conteneur :

```sh
docker compose up -d --force-recreate host1
```

## Dépannage

- **`systemd` ne démarre pas / `Failed to mount cgroup`** : le conteneur doit
  être `privileged: true` et monter `/sys/fs/cgroup` (déjà dans le compose).
  Vérifier que la machine hôte est en cgroup v2 :
  `stat -fc %T /sys/fs/cgroup` doit afficher `cgroup2fs`.
- **Connexion refusée juste après `up`** : `sshd` démarre après systemd, il
  faut compter 2 à 3 s. Voir `docker compose exec host1 systemctl status ssh`.
- **`Permission denied (publickey)`** : la clé `~/.ssh/id_ed25519_mla.pub`
  n'existait pas au premier `up`. Lancer `docker compose down`, supprimer le
  dossier créé à sa place, régénérer la clé, puis `docker compose up -d --build`.
- **SELinux** : les conteneurs `privileged` tournent sans confinement, donc les
  montages passent. Retirer `privileged` casse ce point.
