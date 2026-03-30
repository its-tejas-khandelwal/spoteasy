(function(){
  var INTERVAL = 10 * 60 * 1000;
  function ping(){
    fetch('/health').catch(function(){});
  }
  setInterval(ping, INTERVAL);
})();