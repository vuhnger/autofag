from __future__ import annotations

from collections.abc import Mapping

from autofag.studentweb.components import AjaxBinding

PARTIAL_AJAX = "javax.faces.partial.ajax"
PARTIAL_SOURCE = "javax.faces.source"
PARTIAL_EXECUTE = "javax.faces.partial.execute"
PARTIAL_RENDER = "javax.faces.partial.render"
VIEW_STATE = "javax.faces.ViewState"

AJAX_HEADERS: Mapping[str, str] = {
    "Faces-Request": "partial/ajax",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/xml, text/xml, */*; q=0.01",
}


def build_ajax_body(
    binding: AjaxBinding,
    view_state: str,
    fields: Mapping[str, str] | None = None,
) -> dict[str, str]:
    body: dict[str, str] = {
        PARTIAL_AJAX: "true",
        PARTIAL_SOURCE: binding.source,
        PARTIAL_EXECUTE: binding.process,
        binding.form: binding.form,
        binding.source: binding.source,
    }
    if binding.render:
        body[PARTIAL_RENDER] = binding.render
    body.update(fields or {})
    body[VIEW_STATE] = view_state
    return body
