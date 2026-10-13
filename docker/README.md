# Environnement de test — deux hôtes Debian + systemd

Outillage de test local pour `mla`. **Ne fait pas partie du rendu.**
Deux conteneurs Debian 12 (bookworm) qui bootent `systemd`, avec `sshd`, un
utilisateur non privilégié `mla` (sudo avec mot de passe, comme sur
l'environnement de correction), joignables en SSH depuis la machine hôte.

## Ce que tu obtiens

| Hôte  | IP conteneur  | Port publié (localhost) | User | Password | Clé attendue                  |
|-------|---------------|-------------------------|------|----------|-------------------------------|
| host1 | `172.28.0.11` | `127.0.0.1:2221`        | `mla`| `mla`    | `~/.ssh/id_ed25519_mla`       |
| host2 | `172.28.0.12` | `127.0.0.1:2222`        | `mla`| `mla`    | `~/.ssh/id_ed25519_mla`       |

- `mla` a `sudo` **avec** mot de passe (`/etc/sudoers.d/mla`, pas de
  `NOPASSWD`) — le mot de passe du compte (`mla`) sert à la fois pour l'auth
  SSH (`ssh_password`) et pour `sudo -S` côté modules (`apt`/`service`/
  `sysctl`), pour reproduire l'environnement de correction.
- `PasswordAuthentication` est activé → les 3 modes d'auth du sujet sont testables.
- Les clés d'hôte SSH sont figées dans l'image : elles ne changent qu'au
  **rebuild**, pas à chaque `up`/`down`.

## Prérequis

- Docker Engine + plugin `compose` (v2.15+ pour la clé `cgroup:`).
- Hôte en cgroup v2 (cas de Fedora — déjà vérifié).

## 1. Générer la clé de test (une seule fois)

Le `compose` monte `~/.ssh/id_ed25519_mla.pub` dans les conteneurs. Crée-la
**avant** le premier `up` (sinon Docker crée un dossier à la place du fichier) :

```sh
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_mla -N "" -C mla-test
```

Pour utiliser une autre clé : `export MLA_PUBKEY=/chemin/vers/ta_cle.pub`.

## 2. Construire et démarrer

Depuis ce dossier (`docker/`) :

```sh
docker compose up -d --build
```

Vérifier que systemd est bien up dans les deux conteneurs :

```sh
docker compose ps
docker compose exec host1 systemctl is-system-running   # "running" ou "degraded" = OK
docker compose exec host2 systemctl list-units --type=service --state=running
```

`degraded` est acceptable (un service masqué qui râle) tant que `ssh` et le
reste tournent.

## 3. Se connecter

```sh
# Mode clé explicite (ssh_key_file) — via l'IP conteneur
ssh -i ~/.ssh/id_ed25519_mla mla@172.28.0.11

# Mode user/password (ssh_user + ssh_password) — via le port publié
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -p 2222 mla@127.0.0.1        # password : mla

# Mode "config ~/.ssh par défaut" : ajoute un bloc Host dans ~/.ssh/config
#   Host mla-host1
#       HostName 172.28.0.11
#       User mla
#       IdentityFile ~/.ssh/id_ed25519_mla
# puis : ssh mla-host1

# Vérifier sudo avec mot de passe (c'est ce que apt/service/sysctl font
# en interne via "printf '%s\n' <password> | sudo -S <commande>")
ssh -i ~/.ssh/id_ed25519_mla mla@172.28.0.11 \
    "printf '%s\n' mla | sudo -S systemctl restart ssh && echo OK"
```

Si tu rebuild et que SSH râle sur la clé d'hôte :
`ssh-keygen -R 172.28.0.11` (et `.12`, et `[127.0.0.1]:2221` / `:2222`).

## 4. Remplir l'inventory

Format du sujet. **Utilise les IP conteneur** (`172.28.0.x`, port 22) plutôt que
`127.0.0.1:222x` : sinon les deux hôtes ont la même IP et le préfixe de log par
IP devient ambigu.

```yaml
hosts:
  host1:
    ssh_address: 172.28.0.11
    ssh_port: 22
    ssh_user: mla
    ssh_key_file: ~/.ssh/id_ed25519_mla
  host2:
    ssh_address: 172.28.0.12
    ssh_port: 22
    ssh_user: mla
    ssh_password: mla
```

## 5. Cycle de vie

| Action                                   | Commande                                     |
|------------------------------------------|----------------------------------------------|
| Démarrer                                 | `docker compose up -d`                        |
| Arrêter (garde les conteneurs)           | `docker compose stop`                         |
| Redémarrer                               | `docker compose restart`                      |
| Détruire conteneurs + réseau             | `docker compose down`                         |
| Détruire aussi l'image                   | `docker compose down --rmi local`             |
| Reconstruire à neuf                      | `docker compose build --no-cache && docker compose up -d` |
| Shell root dans un hôte                  | `docker compose exec host1 bash`             |
| Logs de boot systemd                     | `docker compose logs host1`                   |

## Remise à zéro d'un hôte

Pour retester l'idempotence depuis un état propre, le plus simple est de
recréer un conteneur :

```sh
docker compose up -d --force-recreate host1
```

## Dépannage

- **`systemd` ne boote pas / `Failed to mount cgroup`** : le conteneur doit être
  `privileged: true` et monter `/sys/fs/cgroup` (déjà dans le compose). Vérifie
  que l'hôte est en cgroup v2 : `stat -fc %T /sys/fs/cgroup` → `cgroup2fs`.
- **Connexion refusée juste après `up`** : `sshd` démarre après le boot systemd,
  laisse 2–3 s. `docker compose exec host1 systemctl status ssh`.
- **`Permission denied (publickey)`** : la clé `~/.ssh/id_ed25519_mla.pub`
  n'existait pas au premier `up`. Supprime le dossier parasite
  (`docker compose down`, puis vérifie qu'`~/.ssh/id_ed25519_mla.pub` est un
  fichier), régénère la clé, `up --build`.
- **SELinux (Fedora)** : les conteneurs `privileged` tournent non confinés, les
  montages passent. Si tu retires `privileged`, ça cassera.
