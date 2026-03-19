import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from dashsrc.components.dashvis_constants import *
from .general_plot_helpers import make_discr_trial_cmap
from .general_plot_helpers import draw_track_illustration
from scipy.linalg import subspace_angles

import json



def render_plot(PCs, CAs, metadata, height, width, ca_method='mean', vmin=0, vmax=30):
    print(PCs)
    print(CAs)
    print(metadata)
    print("======================")

    # Get available sessions from the PCs data
    available_sessions = PCs.index.get_level_values('session_id').unique()
    print(f"Available sessions: {available_sessions}")
    
    # Filter CAs to only include sessions present in the data
    CAs_filtered = CAs.loc[
        (CAs['from_session_id'].isin(available_sessions)) & 
        (CAs['to_session_id'].isin(available_sessions))
    ].copy()
    
    CAs_filtered.set_index(['from_session_id', 'to_session_id'], inplace=True)
    print(f"Filtered CAs shape: {CAs_filtered.shape}")

    method = ca_method  # Use the passed parameter instead of hardcoded value
    
    # Different methods to process the CAs data
    if method == 'mean':
        CAs_processed = CAs_filtered.mean(axis=1)
        colorbar_title = 'Mean Canonical Angles'
    elif method == 'median':
        CAs_processed = CAs_filtered.median(axis=1)
        colorbar_title = 'Median Canonical Angles'
    elif method == 'aligned_dims_count':
        # Count of aligned dimensions (canonical angles close to 0, < 0.01)
        CAs_processed = (CAs_filtered < 0.01).sum(axis=1)
        colorbar_title = 'Aligned Dims Count'
    elif method == 'unaligned_dims_mean':
        # Mean of unaligned dimensions (canonical angles >= 0.01)
        CAs_unaligned = CAs_filtered[CAs_filtered >= 0.01]
        CAs_processed = CAs_unaligned.mean(axis=1)
        colorbar_title = 'Unaligned Dims Mean'
    elif method == 'unaligned_dims_median':
        # Median of unaligned dimensions (canonical angles >= 0.01)
        CAs_unaligned = CAs_filtered[CAs_filtered >= 0.01]
        CAs_processed = CAs_unaligned.median(axis=1)
        colorbar_title = 'Unaligned Dims Median'
    else:
        # Default to mean if unknown method
        CAs_processed = CAs_filtered.mean(axis=1)
        colorbar_title = 'Mean Canonical Angles'
    
    # Convert to matrix format
    print(CAs_processed)
    CAs_matrix = CAs_processed.unstack(level='to_session_id')
    print(f"CAs matrix shape: {CAs_matrix.shape}")
    print(CAs_matrix)

    # make two rows of subplots
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True,
        row_heights=[0.25, 0.75],  # Top plot 25%, bottom plot 75%
        vertical_spacing=0.05,     # Reduce spacing between plots
        subplot_titles=("Number of PCs for Explained Variance Thresholds", "Cell Assembly Correlations Across Sessions")
    )
    
    
    expl_var = PCs.explained_variance.unstack(level='session_id')
    expl_var = expl_var.cumsum(axis=0)
    
    threshs = [0.5, .8, 0.95]
    nPCs = {}
    for thresh in threshs:
        nPCs[thresh] = (expl_var < thresh).sum(axis=0)
    # plot as separate traces on first row
    for i, (thresh, nPCs) in enumerate(nPCs.items()):
        fig.add_trace(
            go.Scatter(
                x=expl_var.columns,  # Use actual session_ids instead of range
                y=nPCs.values,
                mode='lines+markers',
                name=f'nPCs {int(thresh*100)}% expl. var.',
            ),
            row=1, col=1
        )
    fig.update_yaxes(
        title_text='Number of PCs',
        range=[0, PCs.columns.str.startswith('PC').sum()],
        row=1, col=1
    )
    fig.update_xaxes(
        type='category',
        showticklabels=False,  # Hide x-axis labels on top plot since it's shared
        row=1, col=1
    )
    
    # draw a heatmap of the CAs
    fig.add_trace(
        go.Heatmap(
            z=CAs_matrix.values,
            x=CAs_matrix.index,
            y=CAs_matrix.columns,
            colorscale='Viridis',
            colorbar=dict(title=colorbar_title),
            zmin=vmin,
            zmax=vmax,
        ),
        row=2, col=1
    )
    fig.update_yaxes(
        title_text='To Session',
        range=[len(CAs_matrix.columns)-0.5, -0.5],  # Adjust range to remove padding
        scaleanchor="x2",
        scaleratio=1,
        type='category',
        row=2, col=1
    )
    fig.update_xaxes(
        title_text='From Session',
        constrain="domain",
        type='category',
        range=[-0.5, len(CAs_matrix.index)-0.5],  # Adjust range to remove padding
        row=2, col=1
    )
    
    fig.update_layout(
        height=1200, width=1200,
        showlegend=True,
        margin=dict(l=50, r=50, t=100, b=50),  # Reduce margins
    )

    return fig