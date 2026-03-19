"""
Cell Assembly Detection Toolbox - Python Implementation

A minimal implementation of the cell assembly detection methods described in:
Lopes-dos-Santos V, Ribeiro S, Tort ABL (2013) Detecting cell assemblies in 
large neuronal populations, Journal of Neuroscience Methods.

This implementation includes:
- Toy simulation for generating synthetic neural data with embedded assemblies
- PCA-based assembly pattern detection
- Statistical thresholding using Marcenko-Pastur distribution and permutation tests
- Assembly activity computation
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import zscore
from sklearn.decomposition import PCA
from sklearn.decomposition import FastICA
# import seaborn as sns


class CellAssemblyDetector:
    """Main class for cell assembly detection and analysis."""
    
    def __init__(self):
        self.assembly_templates = None
        self.eigenvalues = None
        self.eigenvectors = None
        
    def toy_simulation(self, n_neurons=20, n_bins=10000, mean_spike_rate=1.0,
                      assembly_neurons=None, n_activations=300, 
                      activation_spike_rate=3.0):
        """
        Generate synthetic neural spike data with embedded cell assemblies.
        
        Parameters:
        -----------
        n_neurons : int
            Number of neurons in the network
        n_bins : int
            Number of time bins
        mean_spike_rate : float
            Mean firing rate for background activity (Poisson parameter)
        assembly_neurons : list of lists
            Each inner list contains neuron indices for one assembly
        n_activations : int
            Number of assembly activation events
        activation_spike_rate : float
            Mean firing rate during assembly activations
            
        Returns:
        --------
        spike_matrix : ndarray
            Spike count matrix (neurons x time_bins)
        """
        # Default assembly configuration
        if assembly_neurons is None:
            assembly_neurons = [[0, 1, 2, 3], [4, 5, 6]]
        
        # Generate background Poisson activity
        spike_matrix = np.random.poisson(mean_spike_rate, (n_neurons, n_bins))
        
        # Add assembly activations
        for assembly in assembly_neurons:
            # Random activation times
            activation_bins = np.random.randint(0, n_bins, n_activations)
            
            # Add coordinated spikes during activations
            for neuron_idx in assembly:
                if neuron_idx < n_neurons:  # Safety check
                    spike_matrix[neuron_idx, activation_bins] = np.random.poisson(
                        activation_spike_rate, n_activations)
        
        return spike_matrix
    
    def marcenko_pastur_threshold(self, q):
        """
        Compute the Marcenko-Pastur threshold for eigenvalue significance.
        
        Parameters:
        -----------
        q : float
            Ratio of time_bins to neurons (should be > 1)
            
        Returns:
        --------
        lambda_max : float
            Maximum eigenvalue expected from random correlations
        """
        if q < 1:
            raise ValueError("Number of time bins must be larger than number of neurons")
        
        lambda_max = (1 + np.sqrt(1/q))**2
        return lambda_max
    
    def circular_shift_control(self, spike_matrix, n_surrogates=20):
        """
        Generate control eigenvalues using circular shift permutations.
        
        Parameters:
        -----------
        spike_matrix : ndarray
            Original spike matrix (neurons x time_bins)
        n_surrogates : int
            Number of surrogate matrices to generate
            
        Returns:
        --------
        control_max_eig : ndarray
            Maximum eigenvalues from surrogate correlation matrices
        """
        n_neurons, n_bins = spike_matrix.shape
        control_max_eig = np.zeros(n_surrogates)
        
        for i in range(n_surrogates):
            # Create surrogate matrix with circular shifts
            surrogate_matrix = np.zeros_like(spike_matrix)
            
            for neuron_idx in range(n_neurons):
                # Random circular shift for each neuron
                shift_amount = np.random.randint(0, n_bins)
                surrogate_matrix[neuron_idx] = np.roll(spike_matrix[neuron_idx], shift_amount)
            
            # Compute correlation matrix and eigenvalues
            z_surrogate = zscore(surrogate_matrix, axis=1)
            corr_matrix = np.corrcoef(z_surrogate)
            corr_matrix = np.nan_to_num(corr_matrix)  # Handle NaN values
            
            eigenvals = np.linalg.eigvals(corr_matrix)
            control_max_eig[i] = np.max(eigenvals)
        
        return control_max_eig
    
    def bin_shuffling_control(self, spike_matrix, n_surrogates=20):
        """
        Generate control eigenvalues using bin shuffling permutations.
        
        Parameters:
        -----------
        spike_matrix : ndarray
            Original spike matrix (neurons x time_bins)
        n_surrogates : int
            Number of surrogate matrices to generate
            
        Returns:
        --------
        control_max_eig : ndarray
            Maximum eigenvalues from surrogate correlation matrices
        """
        n_neurons, n_bins = spike_matrix.shape
        control_max_eig = np.zeros(n_surrogates)
        
        for i in range(n_surrogates):
            # Create surrogate matrix with shuffled bins
            surrogate_matrix = np.zeros_like(spike_matrix)
            
            for neuron_idx in range(n_neurons):
                # Random permutation of time bins for each neuron
                surrogate_matrix[neuron_idx] = np.random.permutation(spike_matrix[neuron_idx])
            
            # Compute correlation matrix and eigenvalues
            z_surrogate = zscore(surrogate_matrix, axis=1)
            corr_matrix = np.corrcoef(z_surrogate)
            corr_matrix = np.nan_to_num(corr_matrix)
            
            eigenvals = np.linalg.eigvals(corr_matrix)
            control_max_eig[i] = np.max(eigenvals)
        
        return control_max_eig
    
    def detect_assemblies(self, spike_matrix, method='PCA', threshold_method='marcenko_pastur',
                         n_surrogates=20, percentile=95):
        """
        Detect cell assemblies from spike matrix.
        
        Parameters:
        -----------
        spike_matrix : ndarray
            Spike count matrix (neurons x time_bins)
        method : str
            Method for pattern extraction ('PCA' or 'ICA')
        threshold_method : str
            Method for statistical threshold ('marcenko_pastur', 'circular_shift', 'bin_shuffling')
        n_surrogates : int
            Number of surrogate matrices for permutation tests
        percentile : float
            Percentile for statistical threshold
            
        Returns:
        --------
        assembly_templates : ndarray
            Assembly patterns (neurons x assemblies)
        n_assemblies : int
            Number of detected assemblies
        """
        n_neurons, n_bins = spike_matrix.shape
        
        # Z-score normalization
        Z = zscore(spike_matrix, axis=1)
        
        # corr_matrix_T = Z @ Z.T
        # print(corr_matrix.shape)
        
        # Compute correlation matrix
        corr_matrix = np.corrcoef(Z)
        
        # plt.imshow(corr_matrix_T)
        # plt.show()
        # plt.imshow(corr_matrix)
        # plt.show()
        # print(corr_matrix_T-corr_matrix)
        # exit()
        
        
        # assert corr_matrix.isna().any() == False, "Correlation matrix contains NaN values"
        corr_matrix = np.nan_to_num(corr_matrix)
        
        # Eigenvalue decomposition
        eigenvals, eigenvecs = np.linalg.eigh(corr_matrix)
        print(eigenvals)
        
        # Sort eigenvalues in descending order
        idx = np.argsort(eigenvals)[::-1]
        eigenvals = eigenvals[idx]
        eigenvecs = eigenvecs[:, idx]
        print(eigenvals)
        
        self.eigenvalues = eigenvals
        self.eigenvectors = eigenvecs
        
        # Determine statistical threshold
        q = n_bins / n_neurons
        
        if threshold_method == 'marcenko_pastur':
            print("Using Marcenko-Pastur distribution for threshold")
            lambda_max = self.marcenko_pastur_threshold(q)
            print(lambda_max)
            
        elif threshold_method == 'circular_shift':
            print("Using circular shift permutation for threshold")
            control_max_eig = self.circular_shift_control(spike_matrix, n_surrogates)
            lambda_max = np.percentile(control_max_eig, percentile)
            
        elif threshold_method == 'bin_shuffling':
            print("Using bin shuffling permutation for threshold")
            control_max_eig = self.bin_shuffling_control(spike_matrix, n_surrogates)
            lambda_max = np.percentile(control_max_eig, percentile)
            
        else:
            raise ValueError("Unknown threshold method")
        
        # Count significant assemblies
        n_assemblies = np.sum(eigenvals > lambda_max)
        print(n_assemblies)
        print(f"Number of assemblies detected: {n_assemblies}")
        
        if n_assemblies == 0:
            self.assembly_templates = np.array([])
            return np.array([]), 0
        
        # Extract assembly patterns
        if method == 'PCA':
            # Use top eigenvectors
            assembly_templates = eigenvecs[:, :n_assemblies]
            
        elif method == 'ICA':
            # Use FastICA on z-scored data
            ica = FastICA(n_components=n_assemblies, random_state=42, max_iter=500)
            ica.fit(Z.T@eigenvecs[:, :n_assemblies])  # ICA expects samples x features
            print(eigenvecs[:, :n_assemblies].shape, ica.components_.shape)
            assembly_templates = eigenvecs[:, :n_assemblies]@ica.components_  # Transpose to neurons x assemblies
            
        else:
            raise ValueError("Unknown pattern extraction method")
        
        self.assembly_templates = assembly_templates
        return assembly_templates, n_assemblies
    
    def compute_assembly_activity(self, spike_matrix, assembly_templates):
        """
        Compute time course of assembly activity.
        
        Parameters:
        -----------
        spike_matrix : ndarray
            Spike count matrix (neurons x time_bins)
        assembly_templates : ndarray
            Assembly patterns (neurons x assemblies)
            
        Returns:
        --------
        assembly_activity : ndarray
            Time course of assembly activity (assemblies x time_bins)
        """
        # Z-score normalization
        z_spike_matrix = zscore(spike_matrix, axis=1)
        
        n_assemblies = assembly_templates.shape[1]
        n_bins = spike_matrix.shape[1]
        assembly_activity = np.zeros((n_assemblies, n_bins))
        
        for assembly_idx in range(n_assemblies):
            # Compute assembly projector (outer product minus diagonal)
            template = assembly_templates[:, assembly_idx]
            projector = np.outer(template, template)
            np.fill_diagonal(projector, 0)  # Remove diagonal elements
            
            # Compute activity time course
            for t in range(n_bins):
                spike_vector = z_spike_matrix[:, t]
                assembly_activity[assembly_idx, t] = spike_vector.T @ projector @ spike_vector
        
        return assembly_activity


def plot_results(spike_matrix, assembly_templates, assembly_activity):
    """
    Visualize the results of assembly detection.
    
    Parameters:
    -----------
    spike_matrix : ndarray
        Original spike matrix
    assembly_templates : ndarray
        Detected assembly patterns
    assembly_activity : ndarray
        Time course of assembly activity
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    
    # Plot correlation matrix
    corr_matrix = np.corrcoef(spike_matrix)
    im1 = axes[0, 0].imshow(corr_matrix, cmap='viridis', aspect='auto')
    axes[0, 0].set_title('Correlation Matrix')
    axes[0, 0].set_xlabel('Neuron')
    axes[0, 0].set_ylabel('Neuron')
    plt.colorbar(im1, ax=axes[0, 0])
    
    # Plot assembly templates
    if assembly_templates.size > 0:
        n_assemblies = assembly_templates.shape[1]
        for i in range(min(n_assemblies, 2)):
            axes[0, 1].stem(assembly_templates[:, i], label=f'Assembly {i+1}')
            break
        axes[0, 1].set_title('Assembly Templates')
        axes[0, 1].set_xlabel('Neuron')
        axes[0, 1].set_ylabel('Weight')
        axes[0, 1].legend()
        
        # Plot assembly activity
        if assembly_activity.size > 0:
            time_window = min(1000, assembly_activity.shape[1])
            for i in range(min(n_assemblies, 2)):
                axes[1, i].plot(assembly_activity[i, :time_window])
                axes[1, i].set_title(f'Assembly {i+1} Activity')
                axes[1, i].set_xlabel('Time Bin')
                axes[1, i].set_ylabel('Activity')
                # break
    
    plt.tight_layout()
    plt.show()


def main():
    """
    Demonstration of the cell assembly detection pipeline.
    """
    print("Cell Assembly Detection - Python Implementation")
    print("=" * 50)
    
    # Initialize detector
    detector = CellAssemblyDetector()
    
    # Generate synthetic data
    print("Generating synthetic neural data...")
    assembly_config = [[0, 1, 2, 3], [4, 5, 6]]
    spike_matrix = detector.toy_simulation(
        n_neurons=20, 
        n_bins=10000,
        assembly_neurons=assembly_config,
        n_activations=300
    )
    
    print(f"Spike matrix shape: {spike_matrix.shape}")
    print(f"Mean firing rate: {np.mean(spike_matrix):.2f} spikes/bin")
    
    # Detect assemblies
    print("\nDetecting cell assemblies...")
    assembly_templates, n_assemblies = detector.detect_assemblies(
        spike_matrix, 
        method='ICA',
        threshold_method='marcenko_pastur'
    )
    
    if n_assemblies > 0:
        print(f"Assembly templates shape: {assembly_templates.shape}")
        
        # Compute assembly activity
        print("\nComputing assembly activity...")
        assembly_activity = detector.compute_assembly_activity(spike_matrix, assembly_templates)
        print(f"Assembly activity shape: {assembly_activity.shape}")
        
        # Visualize results
        print("\nGenerating plots...")
        plot_results(spike_matrix, assembly_templates, assembly_activity)
        
    else:
        print("No significant assemblies detected.")


if __name__ == "__main__":
    main()
