"""
     ██╗ ██████╗ ██╗   ██╗██╗    ██╗  ██╗███████╗██╗     ██████╗
     ██║██╔═══██╗██║   ██║██║    ██║  ██║██╔════╝██║     ██╔══██╗
     ██║██║   ██║██║   ██║██║    ███████║█████╗  ██║     ██████╔╝
██   ██║██║   ██║╚██╗ ██╔╝██║    ██╔══██║██╔══╝  ██║     ██╔═══╝
╚█████╔╝╚██████╔╝ ╚████╔╝ ██║    ██║  ██║███████╗███████╗██║
 ╚════╝  ╚═════╝   ╚═══╝  ╚═╝    ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝

    Inline help panel for ComfyUI Nodes with remote HTML/Markdown support
"""

__author__ = "Alexander G. Morano"
__email__ = "amorano@gmail.com"

import os
import re
import html
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Tuple

try:
    from markdownify import markdownify
except:
    markdownify = None

from aiohttp import web, ClientSession
from loguru import logger

from server import PromptServer

WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS = {}, {}

ROOT = Path(__file__).resolve().parent
ROOT_COMFY = ROOT.parent.parent
ROOT_DOC = ROOT / 'res'

# nodes to skip on import; for online systems; skip Export, Streamreader, etc...
JOV_IGNORE_NODE = ROOT / 'ignore.txt'

JOV_INTERNAL = os.getenv("JOV_INTERNAL", 'false').strip().lower() in ('true', '1', 't')

# direct the documentation output -- used to build jovimetrix-examples
JOV_INTERNAL_DOC = os.getenv("JOV_INTERNAL_DOC", str(ROOT / "_doc"))

# The object_info route data -- cached
COMFYUI_OBJ_DATA = {}

# maximum items to show in help for combo list items
JOV_LIST_MAX = 25

# HTML TEMPLATES
TEMPLATE = {}

# BAD ACTOR NODES -- GITHUB MARKDOWN HATES EMOJI -- SCREW GITHUB MARKDOWN
MARKDOWN = [
    "ADJUST", "BLEND", "CROP", "FLATTEN", "STEREOSCOPIC", "MIDI-MESSAGE",
    "MIDI-FILTER", "STREAM-WRITER"
]

# ==============================================================================
# === DOCUMENTATION ===
# ==============================================================================

def collapse_repeating_parameters(params_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Collapses repeating parameters like `input_blocks.0`,...`input_blocks.10` into 1 parameter `input_blocks.i`."""
    collapsed = {}
    pattern_seen = {}
    for param_category in params_dict:
        collapsed[param_category] = {}
        for param_name, param_type in params_dict[param_category].items():
            pattern = r"\.\d+"
            generic_pattern, n = re.subn(pattern, ".{}", param_name)
            if n > 0:
                letters = (letter for letter in "ijklmnopqrstuvwxyzabcdefgh")
                generic_pattern = re.sub(r"\{\}", lambda _: next(letters), generic_pattern)
                if generic_pattern not in pattern_seen:
                    pattern_seen[generic_pattern] = True
                    collapsed[param_category][generic_pattern] = param_type
            else:
                collapsed[param_category][param_name] = param_type
    return collapsed

def match_combo(lst: List[Any] | Tuple[Any]) -> str:
    """Detects comfy dtype for a combo parameter."""
    types_matcher = {
        "str": "STRING", "float": "FLOAT", "int": "INT", "bool": "BOOLEAN"
    }
    if len(lst) > 0:
        return f"{types_matcher.get(type(lst[0]).__name__, 'STRING')}"
    return "STRING"

def template_load(fname: str) -> Template:
    with open(ROOT_DOC / fname, 'r', encoding='utf-8') as f:
        data = Template(f.read())
    return data

HTML_input_section = template_load('template_section.html')
HTML_input_row = template_load('template_param_input.html')
HTML_output_row = template_load('template_param_output.html')
HTML_template_node = template_load('template_node.html')
HTML_template_node_plain = template_load('template_node_plain.html')

def json2html(json_dict: dict) -> str:
    """Convert JSON to HTML using templates for all HTML elements."""
    name = json_dict['name']
    boop = name.split(' (JOV)')[0].strip()
    root1 = root2 = ""
    template_node = HTML_template_node_plain
    if " (JOV)" in name:
        template_node = HTML_template_node
        boop2 = boop.replace(" ", "%20")
        root1 = f"https://github.com/Amorano/Jovimetrix-examples/blob/master/node/{boop2}/{boop2}.md"
        root2 = f"https://raw.githubusercontent.com/Amorano/Jovimetrix-examples/master/node/{boop2}/{boop2}.png"

    # Generate input content
    input_sections = []
    for k, v in json_dict['input_parameters'].items():
        if not v:
            continue
        rows = []
        for param_key, param_meta in v.items():
            typ = param_meta.get('type', 'UNKNOWN').upper()
            typ = ', '.join([x.strip() for x in typ.split(',')])
            tool = param_meta.get("tooltip", '')
            default = html.escape(str(param_meta.get('default', '')))
            ch = ', '.join(param_meta.get('choice', []))
            rows.append(HTML_input_row.substitute(
                param_key=html.escape(param_key),
                type=typ,
                tooltip=tool,
                default=default,
                choice=ch
            ))

        input_sections.append(HTML_input_section.substitute(
            name=html.escape(k.upper()),
            rows=''.join(rows)
        ))

    # Generate output content
    output_rows = []
    for k, v in json_dict['output_parameters'].items():
        data = v.split('$')
        #desc = '<br>'.join(textwrap.wrap(data[1], 60))
        output_rows.append(HTML_output_row.substitute(
            name=html.escape(k),
            type=html.escape(data[0]),
            description=html.escape(data[1])
        ))

    # Fill in the main template
    description = json_dict['description']
    #if not "<div>" in description and not "<p>" in description:
        #description = markdown.markdown(description)
        # description = html.escape(description)
    description = description.replace('\n', '<br>').replace(f"('", '').replace(f"')", '')

    html_content = template_node.substitute(
        title=html.escape(name),
        name=html.escape(name),
        root1=root1,
        category=html.escape(json_dict['category']),
        documentation=description,
        root2=root2,
        boop=html.escape(boop),
        output_node=json_dict['output_node'],
        input_content=''.join(input_sections),
        output_content=''.join(output_rows)
    )
    return html_content

def get_node_info(node_data: dict) -> Dict[str, Any]:
    """Transform node object_info route result into .html."""
    input_parameters = {}
    for k, node_param_meta in node_data.get('input', {}).items():
        if not k in ["required", "optional"]:
            continue

        input_parameters[k] = {}
        for param_key, param_meta in node_param_meta.items():
            lst = None
            typ = param_meta[0]
            if isinstance(typ, list):
                typ = match_combo(typ)
                lst = param_meta
            input_parameters[k][param_key] = {
                "type": typ
            }
            try:
                meta = param_meta[1]
                if lst is not None:
                    if (choice_list := meta.get('choice', None)) is None:
                        data = [x.replace('_', ' ') for x in lst[0]][:JOV_LIST_MAX]
                        input_parameters[k][param_key]["choice"] = data
                        meta.update(lst[1])
                    else:
                        input_parameters[k][param_key]["choice"] = [choice_list][:JOV_LIST_MAX]
                        meta['default'] = 'dynamic'
                elif (default_top := meta.get('default_top', None)) is not None:
                    meta['default'] = default_top

                # only stuff that makes sense...
                junk = ['default', 'min', 'max']
                meta = node_param_meta[param_key][1]
                if (tip := meta.get("tooltip", None)) is None:
                    junk.append("tooltip")
                    tip = "Unknown Explanation!"
                input_parameters[k][param_key]["tooltip"] = tip
                for scrape in junk:
                    if (val := meta.get(scrape, None)) is not None and val != "":
                        input_parameters[k][param_key][scrape] = val
            except IndexError:
                pass

    return_types = [
        match_combo(x) if isinstance(x, list) or isinstance(x, tuple) else x for x in node_data.get('output', [])
    ]

    output_parameters = {}
    tooltips = node_data.get('output_tooltips', [])
    return_names = [t.lower() for t in node_data.get('output_name', [])]
    for name, typ, tip in zip(return_names, return_types, tooltips):
        output_parameters[name] = '$'.join([typ, tip])

    data = {
        "class": node_data['name'],
        "input_parameters": collapse_repeating_parameters(input_parameters),
        "output_parameters": output_parameters,
        "name": node_data['name'],
        "output_node": node_data['output_node'],
        "category": node_data['category'].strip('\n').strip(),
        "description": node_data['description']
    }
    data[".html"] = json2html(data)
    if markdownify:
        md = markdownify(data[".html"], keep_inline_images_in=True)
        md = md.split('\n')[8:]
        md = '\n'.join([m for m in md if m != ''])
        data[".md"] = md
    return data

def update_nested_dict(d, path, value) -> None:
    keys = path.split('.')
    current = d
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    last_key = keys[-1]

    # Check if the key already exists
    if last_key in current and isinstance(current[last_key], dict):
        current[last_key].update(value)
    else:
        current[last_key] = value

# ==============================================================================
# === API ===
# ==============================================================================

async def object_info(node_class: str, scheme:str, host: str) -> Any:
    global COMFYUI_OBJ_DATA
    if (info := COMFYUI_OBJ_DATA.get(node_class, None)) is None:
        # look up via the route...
        url = f"{scheme}://{host}/object_info/{node_class}"

        # Make an asynchronous HTTP request using aiohttp.ClientSession
        async with ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        info = await response.json()
                        if (data := info.get(node_class, None)) is not None:
                            info = get_node_info(data)
                        else:
                            info = {'.html': f"No data for {node_class}"}
                        COMFYUI_OBJ_DATA[node_class] = info
                    else:
                        info = {'.html': f"Failed to get docs {node_class}, status: {response.status}"}
                        logger.error(info)
            except Exception as e:
                logger.error(f"Failed to get docs {node_class}")
                logger.exception(e)
                info = {'.html': f"Failed to get docs {node_class}\n{e}"}

    return info

@PromptServer.instance.routes.get("/jov_help")
async def jovimetrix_home(req) -> Any:
    data = template_load('home.html')
    return web.Response(text=data.template, content_type='text/html')

@PromptServer.instance.routes.get("/jov_help/doc")
async def jovimetrix_doc(req) -> Any:

    for node_class in NODE_CLASS_MAPPINGS.keys():
        if COMFYUI_OBJ_DATA.get(node_class, None) is None:
            COMFYUI_OBJ_DATA[node_class] = await object_info(node_class, req.scheme, req.host)

        node = NODE_DISPLAY_NAME_MAPPINGS[node_class]
        fname = node.split(" (")[0]
        path = Path(JOV_INTERNAL_DOC.replace("{name}", fname))
        path.mkdir(parents=True, exist_ok=True)

        if JOV_INTERNAL:
            if (md := COMFYUI_OBJ_DATA[node_class].get('.md', None)) is not None:
                with open(str(path / f"{fname}.md"), "w", encoding='utf-8') as f:
                    f.write(md)

            with open(str(path / f"{fname}.html"), "w", encoding='utf-8') as f:
                f.write(COMFYUI_OBJ_DATA[node_class]['.html'])

    return web.json_response(COMFYUI_OBJ_DATA)

@PromptServer.instance.routes.get("/jov_help/doc/{node}")
async def jovimetrix_doc_node_comfy(req) -> Any:
    node_class = req.match_info.get('node')
    if COMFYUI_OBJ_DATA.get(node_class, None) is None:
        COMFYUI_OBJ_DATA[node_class] = await object_info(node_class, req.scheme, req.host)
    return web.Response(text=COMFYUI_OBJ_DATA[node_class]['.html'], content_type='text/html')
