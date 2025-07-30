#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import cairosvg

def convert_svg_to_png(svg_path, dpi=300):
    """
    Convert SVG file to PNG with specified DPI.
    
    Args:
        svg_path (str): Path to SVG file
        dpi (int): Desired DPI for output PNG (default: 300)
    """
    svg_path = Path(svg_path)
    if not svg_path.exists():
        print(f"Error: File {svg_path} does not exist")
        return
    
    # Create output path with same name but .png extension
    png_path = svg_path.with_suffix('.png')
    
    try:
        # Convert SVG to PNG
        # Scale factor calculation: dpi/96 (96 is the default SVG DPI)
        scale = dpi/96.0
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            scale=scale
        )
        print(f"Successfully converted {svg_path} to {png_path} at {dpi} DPI")
    except Exception as e:
        print(f"Error converting {svg_path}: {str(e)}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python svg_to_png_converter.py <svg_file_or_directory> [dpi]")
        print("Example: python svg_to_png_converter.py figure.svg 300")
        print("Example: python svg_to_png_converter.py ./figures/ 300")
        sys.exit(1)
    
    path = sys.argv[1]
    dpi = 300 if len(sys.argv) < 3 else int(sys.argv[2])
    
    if os.path.isdir(path):
        # Convert all SVGs in directory
        for svg_file in Path(path).glob('*.svg'):
            convert_svg_to_png(svg_file, dpi)
    else:
        # Convert single file
        convert_svg_to_png(path, dpi)

if __name__ == "__main__":
    main()
