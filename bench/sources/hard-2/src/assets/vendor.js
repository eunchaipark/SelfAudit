/*! @license DOMPurify 2.0.8 | (c) Cure53 and other contributors | Apache-2.0 OR MPL-2.0 */
(function (global) {
  var VERSION = "2.0.8";
  var ALLOWED = ["b", "i", "em", "strong", "p", "br", "span"];

  function sanitize(dirty) {
    var holder = document.createElement("template");
    holder.innerHTML = String(dirty);
    var nodes = holder.content.querySelectorAll("*");
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (ALLOWED.indexOf(node.nodeName.toLowerCase()) < 0) {
        node.remove();
        continue;
      }
      for (var j = node.attributes.length - 1; j >= 0; j--) {
        var name = node.attributes[j].name;
        if (name.indexOf("on") === 0) {
          node.removeAttribute(name);
        }
      }
    }
    return holder.innerHTML;
  }

  global.DOMPurify = { version: VERSION, sanitize: sanitize, isSupported: true };
})(window);
