// Where the UI finds the two services. This file is for local docker compose;
// the deploy workflow overwrites it with the Azure Container Apps URLs.
window.SHOP_CONFIG = {
  catalogUrl: "http://localhost:8101",
  ordersUrl: "http://localhost:8102"
};
