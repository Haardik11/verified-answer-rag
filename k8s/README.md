# Running this on Kubernetes

These manifests assume a local cluster (tested with `kind`) and images already
built and loaded into it - this isn't set up to pull from a remote registry.

1. Build the images and load them into your cluster:
   ```
   docker compose build
   kind load docker-image verifiedrag-backend:latest --name <your-cluster-name>
   kind load docker-image verifiedrag-frontend:latest --name <your-cluster-name>
   ```

2. Create the secret holding API keys directly from your local `.env` -
   deliberately not committed as YAML, so real keys never end up in git:
   ```
   kubectl create secret generic verifiedrag-secrets --from-env-file=.env
   ```

3. Apply everything:
   ```
   kubectl apply -f k8s/qdrant-pvc.yaml
   kubectl apply -f k8s/backend-deployment.yaml
   kubectl apply -f k8s/frontend-deployment.yaml
   ```

4. Reach it locally:
   ```
   kubectl port-forward svc/backend 8000:8000
   kubectl port-forward svc/frontend 8080:80
   ```
