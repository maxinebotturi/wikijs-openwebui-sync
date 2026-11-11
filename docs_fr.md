# Déploiement - Assistant RAG sur la documentation Wiki.js (via Open WebUI)

Guide complet pour monter un assistant qui répond aux questions à partir de ta
doc Wiki.js, en français **et** en anglais, en citant ses sources.

---

## 1. Vue d'ensemble

La chaîne, de bout en bout :

```
Wiki.js  ──►  export_wiki.py  ──►  dossier de .md  ──►  oikb  ──►  Knowledge Base  ──►  réponse RAG
 (source)      (le pont)          (wiki_md/)          (synchro)    (Open WebUI)      (embedder bge-m3)
```

Le rôle de chaque pièce :

| Pièce | Rôle |
|---|---|
| **Wiki.js** | la source de vérité (ta doc). On la lit via son API GraphQL. |
| **export_wiki.py** | exporte chaque page wiki en fichier `.md` dans un dossier local. C'est le pont, car oikb ne parle pas nativement Wiki.js. |
| **oikb** | outil officiel d'Open WebUI qui synchronise un dossier vers une Knowledge Base : il n'envoie que ce qui a changé (diff SHA-256), ajoute le neuf, **supprime ce qui a disparu**. |
| **Open WebUI** | l'interface de chat + le moteur RAG (découpage, embeddings, recherche, génération). |
| **bge-m3** | le modèle d'embedding multilingue. C'est lui qui fait que « commutateur » retrouve une page qui dit « switch ». |

---

## 2. Pourquoi cette architecture (les 2 décisions clés)

**RAG plutôt qu'un MCP Wiki.js.** Un MCP brancherait l'assistant sur la *recherche
native* de Wiki.js, qui travaille par mots-clés : « commutateur » et « switch » y
sont deux mots sans rapport (test fait, résultats différents). Le RAG vectorise le
*sens*, donc les deux se rejoignent. C'est la couche sémantique qui manquait.

**bge-m3 comme embedder.** Ce pont entre français et jargon anglais ne fonctionne
que si le modèle d'embedding est réellement **cross-lingue**. Un modèle orienté
anglais, ou franco-français, ne rapprocherait pas aussi bien les deux. bge-m3 est
multilingue et c'est précisément ce qui fait marcher ton cas (VSX / switch /
commutateur dans la même requête).

---

## 3. Pré-requis

- **Open WebUI ≥ 0.9.6** - c'est la version qui a introduit les endpoints de
  synchro incrémentale qu'oikb pilote. Sur plus ancien, oikb n'a rien à appeler.
- **Ollama** installé et joignable depuis Open WebUI (il servira aux embeddings).
- **Python 3.10+** (pour oikb et pour le script), avec `requests` pour le script.
- **Accès admin** à Wiki.js (pour le token API) et à Open WebUI (pour régler
  l'embedder et créer la clé API).

---

## 4. Étape 1 - Modèle d'embedding (Ollama)

Récupère le modèle multilingue :

```bash
ollama pull bge-m3
```

---

## 5. Étape 2 - Open WebUI : embedder, Knowledge Base, clé API

**2a - Régler l'embedder AVANT tout import (étape la plus importante).**
*Admin → Settings → Documents* :
- Embedding Engine : **Ollama**
- Embedding Model : **bge-m3**

> ⚠️ Fais-le **avant** le premier sync. Les documents sont vectorisés au moment où
> ils entrent dans la KB : s'ils sont importés avec l'embedder par défaut (souvent
> orienté anglais), ta recherche en français sera mauvaise. Si tu changes
> d'embedder plus tard, il faut **ré-indexer** la KB.

**2b - Créer la Knowledge Base.** *Workspace → Knowledge → +*. Donne-lui un nom
(ex. « Documentation interne »). Ouvre-la : son **ID est dans l'URL**, du type
`/knowledge/8f3a2b1c-1234-…`. Note-le, oikb en a besoin.

**2c - Créer une clé API Open WebUI.** *Settings → Account → API Keys*. Note la clé
(commence par `sk-…`).

---

## 6. Étape 3 - Wiki.js : token API

Dans *Administration → API Access* : active l'API si nécessaire, puis crée un token
avec au minimum le **droit de lecture des pages**. Note-le.

---

## 7. Étape 4 - Exporter le wiki en fichiers .md

C'est le script `export_wiki.py` (fourni en annexe, et en fichier séparé). Il liste
toutes les pages via GraphQL, écrit chaque page en `.md` (avec son titre et son URL
source en tête), et supprime les `.md` orphelins pour propager les suppressions.

```bash
export WIKI_URL="https://ton-wiki.site.fr"
export WIKI_TOKEN="ton_token_wikijs"
export OUT_DIR="$HOME/wiki_md"
python export_wiki.py
```

Tu obtiens un dossier `~/wiki_md/` qui reflète l'arborescence de ton wiki. Lance-le
une première fois à la main pour vérifier qu'il se remplit bien.

> **Raccourci possible :** si le module **Storage → Git** de Wiki.js est activé, ton
> wiki écrit déjà toutes ses pages en `.md` dans un dépôt. Dans ce cas tu peux
> pointer oikb directement sur ce dépôt (dossier local ou `github:org/repo`) et te
> passer complètement du script. À vérifier dans *Administration → Storage*.

---

## 8. Étape 5 - oikb : synchroniser le dossier vers la KB

Installe et configure une fois pour toutes :

```bash
pip install oikb
oikb config set url   http://localhost:3000      # l'URL de ton Open WebUI
oikb config set token sk-ta-cle-openwebui
```

Fais un essai **à blanc** d'abord - il montre ce qui serait ajouté / modifié /
supprimé sans rien toucher :

```bash
oikb sync "$HOME/wiki_md" --kb-id TON_KB_ID --dry-run
```

Si le résultat te convient, lance le vrai sync :

```bash
oikb sync "$HOME/wiki_md" --kb-id TON_KB_ID
```

Relance-le : rien ne se passe tant que rien n'a changé (synchro incrémentale par
empreinte SHA-256). C'est oikb qui gère les doublons, les mises à jour, les
suppressions, et le traitement asynchrone côté serveur - tu n'as rien à coder.

---

## 9. Étape 6 - Automatiser (un seul cron)

Un job, séquentiel : on rafraîchit le dossier, **puis** on synchronise.

```bash
# /etc/cron.d/wiki-rag - toutes les heures
0 * * * *  user  cd /home/user && \
  WIKI_URL="https://ton-wiki.site.fr" WIKI_TOKEN="xxx" OUT_DIR="/home/user/wiki_md" \
  python export_wiki.py && \
  oikb sync /home/user/wiki_md --kb-id TON_KB_ID
```

Un seul horaire, facile à raisonner. Largement suffisant pour un homelab.

---

## 10. Étape 7 - Tester

Dans Open WebUI, ouvre un chat, attache la Knowledge Base (via `#` ou les réglages
du modèle), et pose une question **paraphrasée exprès** :

- Demande en français quelque chose dont la page est rédigée en anglais (ex. « comment
  redémarrer un commutateur ? » alors que la page parle de *switch reboot*).
- Vérifie que la bonne page remonte **et** que la réponse cite sa source.

Si la version anglaise de la page remonte sur une question française, ta couche
sémantique cross-lingue fonctionne : c'est gagné.

---

## 11. Dépannage (les pièges classiques)

- **Mauvaise pertinence en français / le test commutateur↔switch échoue toujours** →
  l'embedder n'est pas réglé sur bge-m3 (cause n°1). Vérifie *Admin → Settings →
  Documents*, puis ré-indexe.
- **Tu as changé d'embedder après coup** → les anciens vecteurs ne sont plus
  comparables. Ré-indexe la KB (ou re-sync après un reset).
- **oikb ne fait rien / erreur d'endpoint** → Open WebUI est en dessous de 0.9.6.
- **« The content provided is empty » (400)** → traitement asynchrone du fichier.
  oikb gère les retries tout seul ; ce message n'apparaît que si tu scriptes les
  appels à la main sans attendre.
- **L'ID de la KB est introuvable** → il est dans l'URL quand tu ouvres la KB
  (`/knowledge/<id>`).
- **oikb ré-uploade tout à chaque passage** → vérifie que les noms de fichiers sont
  stables d'un run à l'autre (le script conserve le chemin wiki comme nom, donc OK ;
  un nom qui change = vu comme suppression + ajout).

---

## 12. Évolutions optionnelles (plus tard, si besoin)

- **Mise à jour en temps réel** (la KB suit la seconde où une page est éditée) :
  `oikb watch` (réagit aux événements du système de fichiers) ou le **daemon oikb**
  avec un webhook, à la place du cron.
- **Précision sur le jargon pointu** (VSX vs VSF, codes, commandes, là où le
  sémantique seul peut hésiter) : ajouter une **recherche hybride** (sémantique +
  mots-clés). C'est un bonus ; le sémantique reste la fondation.

---

## 13. Récapitulatif - qui tourne quand

| Quand | Quoi | Qui |
|---|---|---|
| Une fois, au setup | pull du modèle, réglage embedder, création KB + clés | toi |
| À chaque exécution du cron | wiki → dossier `.md` | `export_wiki.py` |
| À chaque exécution du cron | dossier `.md` → Knowledge Base (incrémental) | `oikb sync` |
| À chaque question | découpage / embeddings / recherche / réponse | Open WebUI |

---

## Annexe - `export_wiki.py` (script complet)

```python
#!/usr/bin/env python3
"""
export_wiki.py - exporte toutes les pages Wiki.js en fichiers .md.

Le dossier produit est destiné à oikb, qui se charge ensuite de la synchro
incrémentale vers Open WebUI (ajout / mise à jour / suppression).

Volontairement bête et robuste : à chaque run on ré-écrit TOUTES les pages,
et on supprime les .md devenus orphelins (pages disparues du wiki). Pas besoin
d'être incrémental ici : oikb ne ré-uploade que ce qui a changé (diff SHA-256).

Usage :
    export WIKI_URL="https://ton-wiki.site.fr"
    export WIKI_TOKEN="ton_token_wikijs"
    export OUT_DIR="./wiki_md"
    python export_wiki.py
"""

import os
import sys

import requests

WIKI_URL   = os.environ.get("WIKI_URL", "https://ton-wiki.site.fr").rstrip("/")
WIKI_TOKEN = os.environ.get("WIKI_TOKEN", "")
OUT_DIR    = os.environ.get("OUT_DIR", "./wiki_md")


def gql(query, variables=None):
    r = requests.post(
        f"{WIKI_URL}/graphql",
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {WIKI_TOKEN}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL: {data['errors']}")
    return data["data"]


def list_pages():
    return gql("{ pages { list(orderBy: PATH) { id path title locale } } }")["pages"]["list"]


def get_content(page_id):
    q = "query($id:Int!){ pages { single(id:$id){ content } } }"
    return gql(q, {"id": page_id})["pages"]["single"]["content"] or ""


def safe_relpath(wiki_path):
    """Transforme un chemin de page wiki en chemin de fichier sûr."""
    rel = wiki_path.strip("/").replace("..", "_")
    return (rel or "index") + ".md"


def export():
    pages = list_pages()
    written = set()

    for p in pages:
        rel = safe_relpath(p["path"])
        dest = os.path.join(OUT_DIR, rel)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

        # en-tête : titre + URL source (pour que le RAG puisse citer la page)
        url = f"{WIKI_URL}/{p['path'].lstrip('/')}"
        header = f"{p['title']}\n\nSource : {url}\n\n---\n\n"
        with open(dest, "w", encoding="utf-8") as f:
            f.write(header + get_content(p["id"]))

        written.add(os.path.abspath(dest))
        print(f"  écrit    {rel}")

    # supprime les .md orphelins -> oikb propagera la suppression vers la KB
    removed = 0
    for root, _dirs, files in os.walk(OUT_DIR):
        for name in files:
            if not name.endswith(".md"):
                continue
            full = os.path.abspath(os.path.join(root, name))
            if full not in written:
                os.remove(full)
                removed += 1
                print(f"  supprimé {os.path.relpath(full, OUT_DIR)}")

    print(f"\n{len(pages)} pages exportées, {removed} orphelins supprimés -> {OUT_DIR}")


if __name__ == "__main__":
    if not WIKI_TOKEN:
        sys.exit("WIKI_TOKEN manquant : export WIKI_TOKEN=... (Admin > API Access)")
    export()
```
