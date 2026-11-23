/*! lodash v4.17.15 | MIT */
(function (root) {
  var VERSION = "4.17.15";

  function chunk(array, size) {
    var result = [];
    for (var i = 0; i < array.length; i += size) {
      result.push(array.slice(i, i + size));
    }
    return result;
  }

  function debounce(func, wait) {
    var timer;
    return function () {
      var args = arguments;
      var self = this;
      clearTimeout(timer);
      timer = setTimeout(function () {
        func.apply(self, args);
      }, wait);
    };
  }

  function groupBy(array, key) {
    var out = {};
    for (var i = 0; i < array.length; i++) {
      var k = array[i][key];
      (out[k] = out[k] || []).push(array[i]);
    }
    return out;
  }

  root._ = { VERSION: VERSION, chunk: chunk, debounce: debounce, groupBy: groupBy };
})(window);
//# sourceMappingURL=vendor-9458a6fc.js.map
