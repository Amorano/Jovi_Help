/**/

import { app } from '../../scripts/app.js'

let PANEL;
const CACHE_DOCUMENTATION = {};
const JOV_HELP_URL = "./api/jov_help/doc";
const JOV_HOME = "./api/jov_help";

if (!window.jov_helpEvents) {
    window.jov_helpEvents = new EventTarget();
}
const jov_helpEvents = window.jov_helpEvents;

async function load_help(name, absolute=false) {
    let url = JOV_HOME;
    if (!absolute) {
        if (name in CACHE_DOCUMENTATION) {
            return CACHE_DOCUMENTATION[name];
        }
        url = `${JOV_HELP_URL}/${name}`;
    }

    // Check if data is already cached
    const result = fetch(url,
        { cache: "no-store" }
    )
        .then(response => {
            if (!response.ok) {
                console.error('Error:', response);
                return `Failed to load documentation: ${name}<br><br>${response.statusText}<br><br>${response.url}`
            }
            return response.text();
        })
        .then(data => {
            // Cache the fetched data
            if (data.startsWith("unknown")) {
                data = `
                    <div align="center">
                        <h3>${data}</h3>
                        <h4>SELECT A NODE TO SEE HELP</h4>
                    </div>
                `;
            };
            CACHE_DOCUMENTATION[name] = data;
            return CACHE_DOCUMENTATION[name];
        })
        .catch(error => {
            console.error('Error:', error);
            return `Failed to load documentation: ${name}\n\n${error}`
        });
    return result;
}

app.extensionManager.registerSidebarTab({
    id: "jov_help.sidebar.help",
    icon: "pi pi-money-bill",
    title: "Joviex Help Lore",
    tooltip: "Inline help panel for ComfyUI extension packs.\nJOVI HELP",
    type: "custom",
    render: async (el) => {
        PANEL = el;
        PANEL.innerHTML = await load_help("home", true);
    }
});

jov_helpEvents.addEventListener('jovi_helpRequested', async (event) => {
    if (PANEL) {
        PANEL.innerHTML = await load_help(event.detail.name);
    }
});

app.registerExtension({
    name: "jov_help.help",
    async init() {
        const styleTagId = 'jovi_help-stylesheet';
        let styleTag = document.getElementById(styleTagId);
        if (styleTag) {
            return;
        }

        document.head.appendChild(Object.assign(document.createElement('link'), {
            id: styleTagId,
            rel: 'stylesheet',
            type: 'text/css',
            href: 'extensions/jovi_help/jovi_help.css'
        }));
	},
    async setup() {
        const onSelectionChange = app.canvas.onSelectionChange;
        app.canvas.onSelectionChange = function(selectedNodes) {
            const me = onSelectionChange?.apply(this);
            if (selectedNodes && Object.keys(selectedNodes).length > 0) {
                const firstNodeKey = Object.keys(selectedNodes)[0];
                const firstNode = selectedNodes[firstNodeKey];
                const data = {
                    class: firstNode?.getNickname?.() || "unknown",
                    name: firstNode.type
                }
                const event = new CustomEvent('jovi_helpRequested', { detail: data });
                jov_helpEvents.dispatchEvent(event);
            }
            return me;
        }
    }
});