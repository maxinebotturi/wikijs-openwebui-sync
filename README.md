# wikijs-openwebui-sync

Turn a [Wiki.js](https://js.wiki/) instance into the knowledge base of an on-premises
[Open WebUI](https://github.com/open-webui/open-webui) assistant, so that the assistant
answers questions **from your own documentation, citing the page it used**, and nothing
ever leaves your network.

```
Wiki.js  -->  export_wiki.py  -->  folder of .md  -->  oikb  -->  Knowledge Base  -->  RAG answer
(source)      (the bridge)        (wiki_md/)         (sync)     (Open WebUI)       (bge-m3 embeddings)
```

| Piece | Role |
|---|---|
| **Wiki.js** | the source of truth. Read through its GraphQL API. |
| **export_wiki.py** (this repo) | exports every page to a `.md` file, with the title and the source URL on top so the answer can cite it. Removes orphaned files when a page is deleted. |
| **[oikb](https://pypi.org/project/oikb/)** | syncs a folder to an Open WebUI knowledge base. Incremental (SHA-256 diff): adds what is new, updates what changed, deletes what disappeared. |
| **Open WebUI** | chat interface and RAG engine (chunking, embeddings, retrieval, generation). |
| **bge-m3** | multilingual embedding model served by Ollama. It is what makes a French question find a page written in English. |

This started as an internal tool for a small IT team whose documentation mixed French
prose and English jargon. The native Wiki.js search is keyword based, so "commutateur"
and "switch" were two unrelated words. Semantic retrieval with a cross-lingual embedder
is the layer that was missing.

## Requirements

- Open WebUI **0.9.6 or later** (first version with the incremental knowledge base endpoints that oikb drives)
- Ollama reachable from Open WebUI
- Python 3.10+, `requests`
- Admin access to Wiki.js (API token) and to Open WebUI (embedder settings, API key)

## Setup in five steps

**1. Pull the embedding model.**

```bash
ollama pull bge-m3
```

**2. Configure Open WebUI, before the first import.**
*Admin > Settings > Documents*: Embedding Engine = Ollama, Embedding Model = bge-m3.
Documents are vectorised when they enter the knowledge base, so changing the embedder later
means re-indexing everything.
Then create a knowledge base (*Workspace > Knowledge*), note its ID from the URL
(`/knowledge/<id>`), and create an API key (*Settings > Account > API Keys*).

**3. Create a Wiki.js API token** with read access to pages (*Administration > API Access*).

**4. Export the wiki.**

```bash
pip install -r requirements.txt
export WIKI_URL="https://wiki.example.org"
export WIKI_TOKEN="your_wikijs_api_token"
export OUT_DIR="$HOME/wiki_md"
python export_wiki.py
```

**5. Sync the folder to the knowledge base.**

```bash
pip install oikb
oikb config set url   http://localhost:3000
oikb config set token sk-your-openwebui-key
oikb sync "$HOME/wiki_md" --kb-id YOUR_KB_ID --dry-run   # shows what would change
oikb sync "$HOME/wiki_md" --kb-id YOUR_KB_ID
```

Run it again: nothing happens until something changes in the wiki.

## Automate it

One sequential cron job: refresh the folder, then sync. See [`examples/wiki-rag.cron`](examples/wiki-rag.cron).

```cron
0 * * * *  user  cd /home/user/wikijs-openwebui-sync && . ./.env && python export_wiki.py && oikb sync "$OUT_DIR" --kb-id "$KB_ID"
```

Put the secrets in a `.env` file (template in [`examples/.env.example`](examples/.env.example)), never in the crontab itself.

## Test it

Attach the knowledge base to a chat and ask a question **paraphrased on purpose**, in the
other language than the page: ask in French about restarting a "commutateur" when the page
talks about a *switch reboot*. If the right page comes back and the answer cites it, the
cross-lingual layer works.

## Troubleshooting

- **Poor relevance in French, the switch/commutateur test fails**: the embedder is not bge-m3. Fix the setting, then re-index.
- **You changed the embedder afterwards**: old vectors are not comparable any more. Re-index the knowledge base.
- **oikb does nothing or reports a missing endpoint**: Open WebUI is older than 0.9.6.
- **`The content provided is empty` (400)**: asynchronous processing on the server. oikb retries by itself; you only see this when scripting the API calls by hand.
- **oikb re-uploads everything each run**: file names must be stable between runs. The script uses the wiki path as the file name, so a renamed page is seen as delete + add, which is correct.

## Shortcut if your wiki already writes to Git

If the Wiki.js **Storage > Git** module is enabled, every page is already a `.md` file in a
repository. Point oikb at that folder and you do not need this script at all.

## Going further

- Real-time updates: `oikb watch` on the export folder, or the oikb daemon with a webhook, instead of cron.
- Sharper results on dense jargon (VSX vs VSF, command names): enable hybrid search (semantic + keyword) in Open WebUI. Semantic retrieval stays the foundation.

## Documentation

The original French deployment guide, with the reasoning behind the architecture, is in
[`docs_fr.md`](docs_fr.md).

## License

MIT. See [LICENSE](LICENSE).
