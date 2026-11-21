# Source issue: momentum direction versus velocity direction

This is a separate mathematical finding, not an applied change to the ZLB
preservation candidate or its frozen concept inventory. It remains visible for
human scientific review. No provider authorship or independent approval is claimed.

The source's equations (60b) and (60c) give momentum increments proportional to
$n$. Its following prose says the maps change only the momentum component along
$M^{-1}n$. For a general mass matrix those directions differ.

Writing $v=M^{-1}p$ resolves the distinction at the level of the displayed
formulas: an increment $p_+-p_-=c n$ produces
$v_+-v_-=c M^{-1}n$. Thus the formulas change momentum along $n$ and velocity
along $M^{-1}n$. The momentum component normal in the $M^{-1}$ inner product is

$$p_\perp=n\frac{n^{\mathsf T}M^{-1}p}{n^{\mathsf T}M^{-1}n}.$$

It lies along $n$, and its remainder is orthogonal to $n$ in that inner product.
This explains why an orthogonality convention alone does not change the
increment direction in the displayed momentum coordinates.

An exact rational example uses $M=\operatorname{diag}(4,1)$, $n=(1,1)$ and
$p_-=(2,1)$. Equation (60c) gives

$$p_+=(-2/5,-7/5),\qquad p_+-p_-=(-12/5,-12/5).$$

The increment is parallel to $n$, but not to $M^{-1}n=(1/4,1)$.
The velocity increment is $(-3/5,-12/5)$, parallel to $M^{-1}n$.
Both kinetic energies are exactly one. These statements were checked using
Python's exact rational arithmetic, without a model call.

A source erratum could replace the prose's momentum-direction assertion by a
momentum-along-$n$ statement and optionally add the velocity interpretation.
Applying that erratum would change the source specification and would require
corresponding source-grounded concept and review updates. The current task
preserves the existing source, including the discrepancy, and does not silently
make that scientific correction.
