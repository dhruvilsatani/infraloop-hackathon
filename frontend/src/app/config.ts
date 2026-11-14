export const PROFILE = {
  name: 'Dhruvil Satani',
  role: 'DevOps & Cloud Platform Engineer',
  bio: 'I built InfraLoop to show teams what is missing before production. If you want the infrastructure itself built or reviewed, you can hire me directly.',
  info: [
    ['Focus', 'Kubernetes, Terraform, CI/CD, observability'],
    ['Stack', 'Kubernetes | Docker | Helm | Terraform | AWS | Python | GitHub Actions'],
    ['Education', 'MSc Computer Science'],
    ['Location', 'Germany'],
  ] as [string, string][],
  email: 'dhruvilsatani00@gmail.com',
  github: 'https://github.com/dhruvilsatani',
  linkedin: '',
};

export const SHOWCASE: boolean = (window as unknown as { SHOWCASE?: boolean }).SHOWCASE === true;
