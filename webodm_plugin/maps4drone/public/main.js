// Adds a "Planejar voo" button to every task that has a map: it opens the planner on that task.
PluginsAPI.Dashboard.addTaskActionButton(function (args) {
  var task = args.task;
  var assets = (task && task.available_assets) || [];
  var hasMap = ["orthophoto.tif", "dsm.tif", "dtm.tif"].some(function (asset) {
    return assets.indexOf(asset) !== -1;
  });
  if (!hasMap) return;

  return React.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-primary",
      title: "Planejar um voo de drone sobre este projeto",
      onClick: function () {
        location.href = "/plugins/maps4drone/index.html?task=" + encodeURIComponent(task.id);
      },
    },
    React.createElement("i", { className: "fa fa-plane fa-fw" }),
    " Planejar voo"
  );
});
